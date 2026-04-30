"""
One-time migration: add no_sms and reminded_at columns to restrings table.

Run from /home/SACCTennis/DEMO-QRs/:
    python migrate_sms_fields.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

existing = [row[1] for row in cur.execute("PRAGMA table_info(restrings)").fetchall()]

if 'no_sms' not in existing:
    cur.execute("ALTER TABLE restrings ADD COLUMN no_sms INTEGER NOT NULL DEFAULT 0")
    print("Added column: no_sms")
else:
    print("Column already exists: no_sms")

if 'reminded_at' not in existing:
    cur.execute("ALTER TABLE restrings ADD COLUMN reminded_at TEXT")
    print("Added column: reminded_at")
else:
    print("Column already exists: reminded_at")

conn.commit()
conn.close()
print("Done.")
