"""
Migration: add pickup_reminder_sent_at column to restrings table.
Run once on PythonAnywhere: python3 add_pickup_reminder_col.py
"""
import sqlite3, os

DB_PATH = os.environ.get("DB_PATH", "/home/SACCTennis/DEMO-QRs/demo.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

existing = {row[1] for row in c.execute("PRAGMA table_info(restrings)").fetchall()}
if 'pickup_reminder_sent_at' not in existing:
    c.execute("ALTER TABLE restrings ADD COLUMN pickup_reminder_sent_at TEXT")
    print("Added column: pickup_reminder_sent_at")
else:
    print("Already exists: pickup_reminder_sent_at")

conn.commit()
conn.close()
print("Done.")
