"""
One-time import script: reads master_cleaned_member_list.csv and loads
members into the SQLite database. Safe to re-run — skips duplicates.

Usage (run from /home/SACCTennis/DEMO-QRs/):
    python import_members.py
"""

import csv
import re
import sqlite3
import sys
from pathlib import Path

CSV_PATH = Path(__file__).parent / 'master_cleaned_member_list.csv'
DB_PATH  = Path(__file__).parent / 'demo.db'


def clean_name(raw):
    # Strip surrounding quotes, replace underscores with spaces
    name = raw.strip().strip('"')
    name = name.replace('_', ' ')
    return name


def clean_number(raw):
    # Strip surrounding quotes and whitespace, remove leading zeros
    num = raw.strip().strip('"').strip()
    # Split numeric prefix from optional letter suffix
    match = re.match(r'^0*(\d+)([A-Za-z]?)$', num)
    if match:
        return match.group(1) + match.group(2).upper()
    return num  # return as-is if pattern doesn't match


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Ensure table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            member_name   TEXT NOT NULL,
            member_number TEXT NOT NULL UNIQUE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_name   ON members(member_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_number ON members(member_number)")

    inserted = 0
    skipped  = 0

    with open(CSV_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name   = clean_name(row.get('Member Name', ''))
            number = clean_number(row.get('Member Number', ''))
            if not name or not number:
                skipped += 1
                continue
            try:
                cur.execute(
                    "INSERT INTO members (member_name, member_number) VALUES (?, ?)",
                    (name, number)
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # Duplicate member_number — skip
                skipped += 1

    conn.commit()
    conn.close()
    print(f"Done. Inserted: {inserted}  Skipped/duplicate: {skipped}")


if __name__ == '__main__':
    main()
