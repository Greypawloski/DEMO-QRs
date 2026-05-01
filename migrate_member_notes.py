"""
Migration: add notes column to members_contact table.
Run from /home/SACCTennis/DEMO-QRs/:
    python migrate_member_notes.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'

conn = sqlite3.connect(DB_PATH)
try:
    conn.execute("ALTER TABLE members_contact ADD COLUMN notes TEXT")
    conn.commit()
    print("Done. Added 'notes' column to members_contact.")
except Exception as e:
    if 'duplicate column' in str(e).lower():
        print("Column already exists — nothing to do.")
    else:
        print(f"Error: {e}")
finally:
    conn.close()
