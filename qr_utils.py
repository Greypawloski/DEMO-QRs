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

_FONT_PATHS_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def _load_font(size, bold=True):
    paths = _FONT_PATHS if bold else _FONT_PATHS_REGULAR
    for path in paths:
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

    display_name = equipment_name + " Demo"

    # Measure text to size the image width to fit the name on one line
    dummy = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    sacc_w, sacc_h = _measure(dummy, "SACC", font_sacc)
    name_w, name_h = _measure(dummy, display_name, font_name)
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

    # SACC centered within the text section; name left-aligned
    sacc_x = text_x + (text_section_w - sacc_w) // 2
    draw.text((sacc_x, text_y),                "SACC",       font=font_sacc, fill='black')
    draw.text((text_x, text_y + sacc_h + gap), display_name, font=font_name, fill='black')

    filename = f"label_{equipment_id}.png"
    img.save(LABEL_DIR / filename, dpi=(300, 300))
    return filename


def generate_string_label(restring_id: int, customer_name: str, string: str,
                           tension: str, strung_by: str, completed_at: str) -> str:
    """Generate a horizontal string label PNG for a completed restring job."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    LABEL_DIR.mkdir(parents=True, exist_ok=True)

    BLUE  = (0, 48, 135)
    BLACK = (20, 20, 20)
    SACC_PHONE = "(210) 824-5951"

    if completed_at:
        dt = datetime.fromisoformat(completed_at).replace(tzinfo=timezone.utc)
        string_date = dt.astimezone(ZoneInfo('America/Chicago')).strftime('%B %-d, %Y')
    else:
        string_date = datetime.now().strftime('%B %-d, %Y')

    W, H   = 1050, 300
    PAD    = 18
    BW     = 4   # border width

    img  = Image.new('RGB', (W, H), 'white')
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle([BW//2, BW//2, W - BW//2 - 1, H - BW//2 - 1], outline=BLUE, width=BW)

    # Logo — left section (fixed smaller size)
    logo_size = 180
    logo_path = Path(__file__).parent / "static" / "sacc-logo.png"
    logo_x = PAD + BW
    logo_y = PAD + BW + (H - 2 * PAD - 2 * BW - logo_size) // 2
    if logo_path.exists():
        logo = Image.open(logo_path).convert('RGBA')
        # Make near-black pixels transparent so logo sits on white background
        data = logo.getdata()
        new_data = [(255, 255, 255, 0) if (r < 60 and g < 60 and b < 60) else (r, g, b, a)
                    for r, g, b, a in data]
        logo.putdata(new_data)
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        bg = Image.new('RGBA', (logo_size, logo_size), (255, 255, 255, 255))
        bg.paste(logo, (0, 0), logo)
        img.paste(bg.convert('RGB'), (logo_x, logo_y))

    # Vertical divider
    div_x = logo_x + logo_size + PAD
    draw.line([(div_x, PAD + BW + 4), (div_x, H - PAD - BW - 4)], fill=BLUE, width=2)

    # Text area
    text_x = div_x + PAD
    text_area_w = W - text_x - PAD - BW
    text_area_h = H - 2 * PAD - 2 * BW

    font_name  = _load_font(34, bold=True)
    font_body  = _load_font(24, bold=True)
    font_small = _load_font(21, bold=True)

    def wrap_text(text, font, max_w):
        words = text.split()
        lines_out, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            if _measure(draw, test, font)[0] <= max_w:
                current = test
            else:
                if current:
                    lines_out.append(current)
                current = word
        if current:
            lines_out.append(current)
        return lines_out or [text]

    string_line = f"{string} @ {tension}"
    string_wrapped = wrap_text(string_line, font_body, text_area_w)
    date_line = f"String Date: {string_date}"
    last_l = SACC_PHONE
    last_r = f"Stringer: {strung_by or 'N/A'}"

    GAP = 6
    _, h_name  = _measure(draw, customer_name, font_name)
    _, h_body  = _measure(draw, "Ag", font_body)
    _, h_small = _measure(draw, last_l, font_small)
    total_h = (h_name + GAP
               + h_body * len(string_wrapped) + GAP * (len(string_wrapped) - 1) + GAP
               + h_body + GAP
               + h_small)
    y = PAD + BW + (text_area_h - total_h) // 2

    def cx(text, font):
        tw, _ = _measure(draw, text, font)
        return text_x + (text_area_w - tw) // 2

    # Name
    draw.text((cx(customer_name, font_name), y), customer_name, font=font_name, fill=BLUE)
    y += h_name + GAP

    # String (possibly wrapped)
    for part in string_wrapped:
        draw.text((cx(part, font_body), y), part, font=font_body, fill=BLACK)
        y += h_body + GAP

    # Date
    draw.text((cx(date_line, font_body), y), date_line, font=font_body, fill=BLACK)
    y += h_body + GAP

    # Bottom row: phone left, stringer right
    wl, _ = _measure(draw, last_l, font_small)
    wr, _ = _measure(draw, last_r, font_small)
    draw.text((text_x, y), last_l, font=font_small, fill=BLACK)
    draw.text((text_x + text_area_w - wr, y), last_r, font=font_small, fill=BLACK)

    filename = f"string_label_{restring_id}.png"
    img.save(LABEL_DIR / filename, dpi=(300, 300))
    return filename
