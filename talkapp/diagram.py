"""Draw bounded, declarative diagrams locally. No model-generated code is run."""
import base64
import io
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


MARKER = '<<<LOCAL_DIAGRAM>>>'
REQUEST = re.compile(r'(?:画|绘制|生成|做|出|给我|来|要|想看)[^。！？\n]{0,24}(?:流程图|结构图|框图|示意图|接线图|连接图|电路图|拓扑图)|^(?:流程图|结构图|框图|接线图|示意图)[。！!？?]*$')
INSTRUCTIONS = '''
用户要求示意图。应用可在本地绘制方框、连线、箭头和中文；无需生成图片链接或代码。
先写简短文字说明，再独立一行写 <<<LOCAL_DIAGRAM>>>，下一行直接给 JSON，不用代码块：
{"title":"LED 接线示意","nodes":[{"id":"a","label":"低压电源"},{"id":"b","label":"电阻"}],"links":[{"from":"a","to":"b","label":"电源正极 → 电阻一端"}]}
按阅读顺序列出 2–8 个方框，每个 id 唯一，最多 10 条有向连接。方框名最多 18 字；接线的连接说明写清起点和终点引脚，最多 32 字。不要虚构型号、引脚或面包板孔位；不知道时说明需要补充什么，不给误导性接线图。只在最终回答输出绘图段。'''


def _label(value, size):
    return ' '.join(value.split())[:size] if isinstance(value, str) else ''


def render(payload):
    """Render a valid JSON diagram as a JPEG data URL; invalid specs return None."""
    if not payload or len(payload) > 6500:
        return None
    try:
        spec = json.loads(payload)
        nodes, links = spec['nodes'], spec['links']
        if not isinstance(nodes, list) or not 2 <= len(nodes) <= 8:
            return None
        if not isinstance(links, list) or not 1 <= len(links) <= 10:
            return None
        indexed = {}
        for node in nodes:
            ident, name = node['id'], _label(node['label'], 18)
            if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,24}', ident) or ident in indexed or not name:
                return None
            indexed[ident] = (len(indexed), name)
        edges = []
        for edge in links:
            start, end = indexed[edge['from']][0], indexed[edge['to']][0]
            if start == end:
                return None
            edges.append((start, end, _label(edge.get('label'), 32)))
        title = _label(spec.get('title'), 27) or '连接示意图'
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None

    width = 1024
    top, row, left, right = 100, 92, 38, 550
    legend_y = top + len(indexed) * row + 22
    height = legend_y + 52 + 47 * len(edges)
    palette = ('#087d94', '#a04b0e', '#5d48a7', '#207040', '#a53669')
    font_path = str(Path(__file__).resolve().parents[1] / 'assets/fonts/roboto_regular.ttf')
    title_font, node_font, small_font = (ImageFont.truetype(font_path, size) for size in (34, 26, 23))
    with Image.new('RGB', (width, height), '#f1f6fa') as image:
        draw = ImageDraw.Draw(image)
        draw.text((left, 30), title, font=title_font, fill='#142c40')
        for index, name in indexed.values():
            y = top + index * row
            draw.rounded_rectangle((left, y, right, y + 72), radius=12, fill='white', outline='#526a7e', width=3)
            draw.text(((left + right) / 2, y + 36), name, font=node_font, anchor='mm', fill='#142c40')
        ports = [[] for _ in nodes]
        for i, (start, end, _) in enumerate(edges):
            ports[start].append(i)
            ports[end].append(i)
        for i, (start, end, label) in enumerate(edges):
            color = palette[i % len(palette)]
            lane = 584 + i * 42
            def port(index):
                return top + index * row + 8 + (ports[index].index(i) + 1) * 56 // (len(ports[index]) + 1)
            y, ty = port(start), port(end)
            draw.line(((right, y), (lane, y), (lane, ty), (right, ty)), fill=color, width=3)
            draw.polygon(((right, ty), (right + 11, ty - 4), (right + 11, ty + 4)), fill=color)
            badge_y = (y + ty) // 2
            draw.ellipse((lane - 14, badge_y - 14, lane + 14, badge_y + 14), fill=color)
            draw.text((lane, badge_y), str(i + 1), font=small_font, anchor='mm', fill='white')
            caption = label or f'{nodes[start]["label"][:16]} → {nodes[end]["label"][:16]}'
            draw.text((left, legend_y + 47 * i), f'{i + 1}. {caption}', font=small_font, fill=color)
        with io.BytesIO() as output:
            image.save(output, format='JPEG', quality=88)
            return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
