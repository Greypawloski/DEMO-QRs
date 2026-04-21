import os

QR_BASE_URL    = os.environ.get("QR_BASE_URL", "http://localhost:5000")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SECRET_KEY     = os.environ.get("SECRET_KEY", "dev-secret-key-change-before-use")
DB_PATH        = os.environ.get("DB_PATH", "demo.db")
RETIRE_PIN     = os.environ.get("RETIRE_PIN", "1904")
STAFF_NAMES    = [n.strip() for n in os.environ.get("STAFF_NAMES", "").split(",") if n.strip()]

TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID",  "")
TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN",   "")
TWILIO_FROM_NUMBER  = os.environ.get("TWILIO_FROM_NUMBER",  "")
