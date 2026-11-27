"""Render an invitation on desktop; decode camera captures on Android."""
from io import BytesIO


def image_bytes(invitation):
    import qrcode
    img = qrcode.make(invitation, box_size=6, border=4)
    png = BytesIO()
    img.save(png, format='PNG')
    return png.getvalue()


def validate_invitation(text, prefix):
    if not text.startswith(prefix) or len(text) > 512:
        raise ValueError('不是对应的配对二维码')
    return text


def decode_android(photo, *, prefix=None):
    from PIL import Image, ImageOps

    with Image.open(photo) as original:
        original.draft('L', (1280, 1280))
        image = ImageOps.exif_transpose(original).convert('L')
        image.thumbnail((1600, 1600))
    return decode_luminance(image.tobytes(), image.width, image.height, prefix=prefix)


def decode_luminance(data, width, height, *, prefix=None):
    from jnius import autoclass
    from .lan_pairing import PREFIX
    # ZXing accepts a byte[] of luminance values; no RGB int array or native
    # Python extension is required. The Android camera does not get chat data.
    source = autoclass('com.google.zxing.PlanarYUVLuminanceSource')(
        bytearray(data), width, height, 0, 0, width, height, False)
    binary = autoclass('com.google.zxing.BinaryBitmap')(
        autoclass('com.google.zxing.common.HybridBinarizer')(source))
    hints = autoclass('java.util.HashMap')()
    hints.put(autoclass('com.google.zxing.DecodeHintType').TRY_HARDER, autoclass('java.lang.Boolean').TRUE)
    text = str(autoclass('com.google.zxing.qrcode.QRCodeReader')().decode(binary, hints).getText())
    return validate_invitation(text, PREFIX if prefix is None else prefix)
