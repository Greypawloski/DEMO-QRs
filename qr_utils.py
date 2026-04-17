import qrcode
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


def _measure(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


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
    """Landscape label: QR on left, SACC + equipment name on right."""
    qr_path = QR_DIR / f"equipment_{equipment_id}.png"
    if not qr_path.exists():
        generate_qr(equipment_id, base_url)

    LABEL_DIR.mkdir(parents=True, exist_ok=True)

    PAD      = 10
    IMG_H    = 160
    QR_SIZE  = IMG_H - 2 * PAD   # 140 — fills the tape height

    font_sacc = _load_font(34)
    font_name = _load_font(22)

    # Measure text to size the image width to fit the name on one line
    dummy = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    sacc_w, sacc_h = _measure(dummy, "SACC", font_sacc)
    name_w, name_h = _measure(dummy, equipment_name, font_name)
    gap      = 8   # vertical gap between SACC and name lines
    text_gap = 16  # horizontal gap between QR and text block

    text_section_w = max(sacc_w, name_w)
    IMG_W = PAD + QR_SIZE + text_gap + text_section_w + PAD

    img  = Image.new('RGB', (IMG_W, IMG_H), 'white')
    draw = ImageDraw.Draw(img)

    # QR code — left side, vertically centered
    qr_img = Image.open(qr_path).convert('RGB').resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
    img.paste(qr_img, (PAD, PAD))

    # Text block — right side, vertically centered as a unit
    text_x      = PAD + QR_SIZE + text_gap
    block_h     = sacc_h + gap + name_h
    text_y      = (IMG_H - block_h) // 2

    draw.text((text_x, text_y),                   "SACC",         font=font_sacc, fill='black')
    draw.text((text_x, text_y + sacc_h + gap),    equipment_name, font=font_name, fill='black')

    filename = f"label_{equipment_id}.png"
    img.save(LABEL_DIR / filename, dpi=(300, 300))
    return filename
