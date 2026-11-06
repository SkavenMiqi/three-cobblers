"""Reproducible TalkApp black-titanium/VFD brand artwork."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets' / 'brand'


def font(size):
    path = ROOT / 'assets/fonts/roboto_regular.ttf'
    return ImageFont.truetype(str(path), size)


def logo(size=1024):
    image = Image.new('RGBA', (1024, 1024), (9, 12, 15, 255))
    draw = ImageDraw.Draw(image)
    for y in range(1024):
        value = int(25 - y * 12 / 1024)
        draw.line((0, y, 1024, y), fill=(value, value + 3, value + 7))
    draw.rounded_rectangle((68, 68, 956, 956), radius=180, fill=(14, 19, 23), outline=(75, 87, 95), width=5)
    draw.rounded_rectangle((90, 90, 934, 934), radius=158, outline=(33, 43, 49), width=3)
    # An angular speech chassis and a calibrated T-shaped data bus.
    shape = [(245, 248), (705, 248), (779, 322), (779, 658), (700, 737),
             (492, 737), (330, 826), (350, 737), (245, 737)]
    glow = Image.new('RGBA', image.size)
    gd = ImageDraw.Draw(glow)
    gd.line(shape + [shape[0]], fill=(0, 225, 200, 150), width=25, joint='curve')
    image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(24)))
    draw = ImageDraw.Draw(image)
    draw.line(shape + [shape[0]], fill=(0, 231, 197), width=13, joint='curve')
    draw.polygon([(319, 334), (679, 334), (679, 408), (540, 408), (540, 642),
                  (459, 642), (459, 408), (319, 408)], fill=(43, 202, 255))
    draw.rectangle((319, 334, 679, 346), fill=(149, 239, 255))
    draw.rectangle((628, 571, 682, 625), fill=(255, 98, 20))
    for x in (204, 820):
        for y in (199, 825):
            draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=(63, 76, 84))
            draw.line((x - 5, y, x + 5, y), fill=(12, 18, 23), width=3)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    logo().save(ASSETS / 'icon.png')
    logo(256).save(ASSETS / 'badge.png')
    canvas = Image.new('RGB', (1080, 1920), (7, 10, 13))
    draw = ImageDraw.Draw(canvas)
    for x in range(36, 1080, 48):
        for y in range(36, 1920, 48):
            draw.point((x, y), fill=(23, 37, 42))
    emblem = logo(360)
    canvas.paste(emblem, (360, 570), emblem)
    draw.text((540, 985), 'TALK', font=font(84), fill=(224, 239, 239), anchor='mm')
    draw.text((540, 1064), 'PERSONAL AI TERMINAL', font=font(25), fill=(36, 202, 246), anchor='mm')
    draw.line((310, 1140, 770, 1140), fill=(42, 62, 69), width=2)
    draw.rectangle((310, 1139, 430, 1142), fill=(0, 231, 197))
    draw.text((540, 1670), 'THINK  /  CONNECT  /  CREATE', font=font(20), fill=(90, 108, 115), anchor='mm')
    canvas.save(ASSETS / 'presplash.png')
    print('BRAND_ASSETS_READY', ASSETS)


if __name__ == '__main__':
    main()
