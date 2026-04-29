"""
Import script: reads Member_info_complete.csv and:
  1. Replaces the members table (used for autocomplete) with fresh name+number data
  2. Populates members_contact table with all columns (name, number, email, phone)

Usage (run from /home/SACCTennis/DEMO-QRs/):
    python import_members_full.py

Safe to re-run — clears and reloads both tables each time.
"""

import csv
import re
import sqlite3
import sys
from pathlib import Path

CSV_PATH = Path(__file__).parent / 'Member_info_complete.csv'
DB_PATH  = Path(__file__).parent / 'demo.db'


def clean_name(raw):
    return raw.strip().strip('"').replace('_', ' ')


def clean_number(raw):
    num = raw.strip().strip('"').strip()
    match = re.match(r'^0*(\d+)([A-Za-z]?)$', num)
    if match:
        return match.group(1) + match.group(2).upper()
    return num


def clean_field(raw):
    val = raw.strip().strip('"').strip() if raw else ''
    return val if val else None


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Ensure tables exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            member_name   TEXT NOT NULL,
            member_number TEXT NOT NULL UNIQUE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_name   ON members(member_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_number ON members(member_number)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS members_contact (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            member_name   TEXT NOT NULL,
            member_number TEXT NOT NULL UNIQUE,
            email1        TEXT,
            email2        TEXT,
            phone1        TEXT,
            phone2        TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_contact_name   ON members_contact(member_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_contact_number ON members_contact(member_number)")

    # Clear both tables for fresh load
    cur.execute("DELETE FROM members")
    cur.execute("DELETE FROM members_contact")

    members_inserted  = 0
    contact_inserted  = 0
    skipped           = 0

    with open(CSV_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name   = clean_name(row.get('Member Name', ''))
            number = clean_number(row.get('Member Number', ''))
            email1 = clean_field(row.get('Email 1', ''))
            email2 = clean_field(row.get('Email 2', ''))
            phone1 = clean_field(row.get('Phone 1', ''))
            phone2 = clean_field(row.get('Phone 2', ''))

            if not name or not number:
                skipped += 1
                continue

            try:
                cur.execute(
                    "INSERT INTO members (member_name, member_number) VALUES (?, ?)",
                    (name, number)
                )
                members_inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
                continue

            cur.execute(
                """INSERT INTO members_contact
                   (member_name, member_number, email1, email2, phone1, phone2)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, number, email1, email2, phone1, phone2)
            )
            contact_inserted += 1

    conn.commit()
    conn.close()
    print(f"Done.")
    print(f"  members table:         {members_inserted} inserted, {skipped} skipped")
    print(f"  members_contact table: {contact_inserted} inserted")


if __name__ == '__main__':
    main()
