"""
Migration: add preference columns to members_contact.
Run once on PythonAnywhere: python add_member_prefs.py
"""
import sqlite3, os

DB_PATH = os.environ.get("DB_PATH", "demo.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

columns = [
    ("racquet_used",     "TEXT"),
    ("shoe_size",        "TEXT"),
    ("skirt_short_size", "TEXT"),
    ("hat_size",         "TEXT"),
    ("clothing_brand",   "TEXT"),
    ("grip_size",        "TEXT"),
]

existing = {row[1] for row in c.execute("PRAGMA table_info(members_contact)").fetchall()}

for col, typ in columns:
    if col not in existing:
        c.execute(f"ALTER TABLE members_contact ADD COLUMN {col} {typ}")
        print(f"Added column: {col}")
    else:
        print(f"Already exists: {col}")

conn.commit()
conn.close()
print("Done.")
