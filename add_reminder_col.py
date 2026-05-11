"""
Migration: add reminder_sent_at column to checkouts table.
Run once on PythonAnywhere: python add_reminder_col.py
"""
import sqlite3, os

DB_PATH = os.environ.get("DB_PATH", "/home/SACCTennis/DEMO-QRs/demo.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

existing = {row[1] for row in c.execute("PRAGMA table_info(checkouts)").fetchall()}
if 'reminder_sent_at' not in existing:
    c.execute("ALTER TABLE checkouts ADD COLUMN reminder_sent_at TEXT")
    print("Added column: reminder_sent_at")
else:
    print("Already exists: reminder_sent_at")

conn.commit()
conn.close()
print("Done.")
