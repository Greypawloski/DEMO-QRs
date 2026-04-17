import qrcode
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

QR_DIR    = Path(__file__).parent / "static" / "qrcodes"
LABEL_DIR = Path(__file__).parent / "static" / "labels"

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _load_font(size):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_centered(draw, y, text, font, img_w, fill='black'):
    x = (img_w - _text_width(draw, text, font)) // 2
    draw.text((x, y), text, font=font, fill=fill)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]  # return text height


def generate_qr(equipment_id: int, base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/checkout/{equipment_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    filename = f"equipment_{equipment_id}.png"
    QR_DIR.mkdir(parents=True, exist_ok=True)
    img.save(QR_DIR / filename)
    return filename


def generate_label(equipment_id: int, equipment_name: str, base_url: str) -> str:
    """Generate an 18mm P-touch label: SACC header + QR code + equipment name."""
    qr_path = QR_DIR / f"equipment_{equipment_id}.png"
    if not qr_path.exists():
        generate_qr(equipment_id, base_url)

    LABEL_DIR.mkdir(parents=True, exist_ok=True)

    IMG_W   = 220
    QR_SIZE = 172
    PAD     = 8

    font_title = _load_font(26)
    font_name  = _load_font(14)

    # Wrap name to fit label width (approx 20 chars per line at font size 14)
    lines = textwrap.wrap(equipment_name, width=22) or [equipment_name]

    # Measure total height
    dummy_img  = Image.new('RGB', (IMG_W, 10))
    dummy_draw = ImageDraw.Draw(dummy_img)
    title_h    = dummy_draw.textbbox((0, 0), "SACC", font=font_title)[3]
    line_h     = dummy_draw.textbbox((0, 0), "A", font=font_name)[3] + 3
    name_block = line_h * len(lines)

    total_h = PAD + title_h + PAD + QR_SIZE + PAD + name_block + PAD

    img  = Image.new('RGB', (IMG_W, total_h), 'white')
    draw = ImageDraw.Draw(img)

    y = PAD
    _draw_centered(draw, y, "SACC", font_title, IMG_W)
    y += title_h + PAD

    qr_img = Image.open(qr_path).convert('RGB').resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
    img.paste(qr_img, ((IMG_W - QR_SIZE) // 2, y))
    y += QR_SIZE + PAD

    for line in lines:
        _draw_centered(draw, y, line, font_name, IMG_W)
        y += line_h

    filename = f"label_{equipment_id}.png"
    img.save(LABEL_DIR / filename, dpi=(300, 300))
    return filename
