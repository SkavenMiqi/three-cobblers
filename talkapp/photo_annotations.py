"""Optional visual annotations from a text reply; pixels are drawn locally."""
import base64
import io
import json
import math
import re

from PIL import Image, ImageDraw, ImageFont


MARKER = '<<<PHOTO_MARKS>>>'
INSTRUCTIONS = '''
如果在当前用户消息所附照片上指出可见位置确实比文字更有用（例如定位部件、可疑区域或步骤），
先正常写完回答，再在独立一行写 <<<PHOTO_MARKS>>>，之后只写一行 JSON，不用代码块：
{"image":1,"marks":[{"kind":"circle","box":[150,220,410,540],"label":"疑似松动的接口"},
{"kind":"arrow","points":[750,200,560,420],"label":"建议补拍这里"}]}
image 从 1 开始，只从当前用户消息所附图片中选最有帮助的一张，按附图顺序编号。由应用实际绘制，不要声称无法画图。
坐标为 0–1000 的整数，原点在图片左上，x 向右、y 向下。圈用左上和右下，箭头用起点和箭头尖端。
最多 6 处，每条标签不超过 32 字，推测要说明是推测。看不清、无法准确定位或文字已足够时，
不要输出标注段。调用软件工具的中间轮次不要输出标注段，只在最终回答中按需输出。'''

FOLLOW_UP = re.compile(
    r'(?:图|照片|画面).{0,16}(?:标(?:注|出|记|一下|下)|圈(?:出|一下|下|起来)|画(?:个)?箭头)'
    r'|(?:标注|标出|圈出|圈一下).{0,12}(?:图|照片|画面)'
    r'|^(?:请)?(?:帮我|给我)?(?:标一下|标注一下|圈一下|画个箭头)[吧。！!？?]*$'
)


def reuse_previous_photo(path):
    """Attach branch-local originals to a copy of the current request, not to history."""
    from .client import image_list

    current = path[-1]
    if current.get('image') or not FOLLOW_UP.search(current['text'].strip()):
        return path, False
    for index in range(len(path) - 2, -1, -1):
        source = path[index]
        if source['role'] == 'user' and image_list(source.get('image')):
            result = list(path)
            result[index] = dict(source, image=None)
            result[-1] = dict(current, image=source['image'])
            return result, True
    return path, False


def split_reply(text, *, streaming=False, marker=MARKER):
    # Also hide a marker that is still being streamed, without hiding normal text.
    lines = text.split('\n')
    for index, line in enumerate(lines):
        candidate = line.lstrip()
        if candidate.startswith(marker):
            payload = '\n'.join([candidate[len(marker):], *lines[index + 1:]]).strip()
            return '\n'.join(lines[:index]).rstrip(), payload
    tail = lines[-1].lstrip()
    if tail and marker.startswith(tail) and (streaming or len(tail) >= 8):
        return '\n'.join(lines[:-1]).rstrip(), ''
    return text, ''


def annotated_photo(payload, photos, *, reused=False):
    """Return (JPEG data URL, numbered legend), or nothing for invalid/empty output."""
    if not payload or len(payload) > 4096:
        return None
    try:
        spec = json.loads(payload)
        index, marks = spec['image'], spec['marks']
        if type(index) is not int or not 1 <= index <= len(photos) or not isinstance(marks, list):
            return None
    except (ValueError, KeyError, TypeError, RecursionError):
        return None

    valid = []
    for mark in marks[:6]:
        if not isinstance(mark, dict):
            continue
        kind = mark.get('kind')
        coords = mark.get('box') if kind == 'circle' else mark.get('points')
        label = mark.get('label')
        if (kind not in ('circle', 'arrow') or not isinstance(coords, list) or len(coords) != 4 or
                not all(type(value) is int and 0 <= value <= 1000 for value in coords) or
                not isinstance(label, str) or not label.strip()):
            continue
        x, y, tx, ty = coords
        if (kind == 'circle' and (x >= tx or y >= ty)) or (kind == 'arrow' and (x, y) == (tx, ty)):
            continue
        valid.append((kind, coords, ' '.join(label.split())[:32]))
    if not valid:
        return None

    with Image.open(io.BytesIO(base64.b64decode(photos[index - 1].split(',', 1)[1], validate=True))) as source:
        source.thumbnail((1600, 1600))
        with source.convert('RGB') as picture:
            _draw_marks(picture, valid)
            with io.BytesIO() as output:
                picture.save(output, format='JPEG', quality=85)
                data = 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
    # Escape Markdown/link syntax in short labels so a model-supplied caption is plain text.
    escapes = str.maketrans({c: '\\' + c for c in '\\`*_[]<>!|'})
    legend = '\n'.join(f'{number}. {label.translate(escapes)}'
                       for number, (_, _, label) in enumerate(valid, 1))
    source = '上一组照片的' if reused else '本次'
    return data, f'AI 标注 · {source}第 {index} 张图（位置为估计）\n\n' + legend


def _draw_marks(picture, marks):
    from pathlib import Path
    draw = ImageDraw.Draw(picture)
    width, height = picture.size
    stroke = max(2, min(width, height) // 130)
    radius = max(8, stroke * 3)
    font = ImageFont.truetype(str(Path(__file__).resolve().parents[1] / 'assets/fonts/roboto_regular.ttf'), radius * 2)
    color = '#ffda44'
    for number, (kind, coords, _) in enumerate(marks, 1):
        x, y, tx, ty = (round(value * (dimension - 1) / 1000)
                        for value, dimension in zip(coords, (width, height, width, height)))
        if kind == 'circle':
            draw.ellipse((x, y, tx, ty), outline='black', width=stroke + 3)
            draw.ellipse((x, y, tx, ty), outline=color, width=stroke)
        else:
            angle = math.atan2(ty - y, tx - x)
            wings = [(round(tx - radius * math.cos(angle + side)), round(ty - radius * math.sin(angle + side)))
                     for side in (-.55, .55)]
            for ink, thickness in (('black', stroke + 3), (color, stroke)):
                draw.line(((x, y), (tx, ty)), fill=ink, width=thickness)
                draw.line((wings[0], (tx, ty), wings[1]), fill=ink, width=thickness)
        bx, by = min(max(x, radius), width - radius - 1), min(max(y, radius), height - radius - 1)
        draw.ellipse((bx - radius, by - radius, bx + radius, by + radius), fill=color, outline='black', width=2)
        draw.text((bx, by), str(number), anchor='mm', font=font, fill='black')
