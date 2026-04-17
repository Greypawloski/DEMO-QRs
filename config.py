import os

QR_BASE_URL    = os.environ.get("QR_BASE_URL", "http://localhost:5000")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SECRET_KEY     = os.environ.get("SECRET_KEY", "dev-secret-key-change-before-use")
DB_PATH        = os.environ.get("DB_PATH", "demo.db")
RETIRE_PIN     = os.environ.get("RETIRE_PIN", "1904")
