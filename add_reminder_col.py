"""
Migration: add reminder_sent_at column to checkouts table.
Run once on PythonAnywhere: python add_reminder_col.py
"""
import sqlite3, os

DB_PATH = os.environ.get("DB_PATH", "/home/SACCTennis/DEMO-QRs/demo.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

existing = {row[1] for row in c.execute("PRAGMA table_info(checkouts)").fetchall()}
for col in ('reminder_sent_at', 'second_reminder_sent_at'):
    if col not in existing:
        c.execute(f"ALTER TABLE checkouts ADD COLUMN {col} TEXT")
        print(f"Added column: {col}")
    else:
        print(f"Already exists: {col}")

conn.commit()
conn.close()
print("Done.")
