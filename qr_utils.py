import qrcode
from pathlib import Path

QR_DIR = Path(__file__).parent / "static" / "qrcodes"


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
