"""
One-time script: backfill phone numbers from checkout and restring history
into members_contact for any member whose number matches the directory.

Uses the same rules as the live sync:
  - phone1 empty          → fill phone1
  - phone1 matches        → skip
  - phone1 taken, phone2 empty   → fill phone2
  - phone1 taken, phone2 matches → skip
  - both taken, both different   → overwrite phone1

Run from /home/SACCTennis/DEMO-QRs/:
    python backfill_phones.py
"""

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'


def digits(s):
    return re.sub(r'\D', '', s or '')


def format_phone(phone):
    d = digits(phone)
    if len(d) == 10:
        return f'{d[:3]}-{d[3:6]}-{d[6:]}'
    return phone


def sync_phone(cur, member_number, submitted_phone):
    if not member_number or member_number == 'Non-member' or not submitted_phone:
        return False
    submitted_digits = digits(submitted_phone)
    if not submitted_digits:
        return False

    row = cur.execute(
        "SELECT id, phone1, phone2 FROM members_contact WHERE member_number = ?",
        (member_number,)
    ).fetchone()
    if not row:
        return False

    p1_digits = digits(row[1])
    p2_digits = digits(row[2])

    if submitted_digits == p1_digits or submitted_digits == p2_digits:
        return False  # already on file

    formatted = format_phone(submitted_phone)
    if not p1_digits:
        cur.execute("UPDATE members_contact SET phone1 = ? WHERE id = ?", (formatted, row[0]))
    elif not p2_digits:
        cur.execute("UPDATE members_contact SET phone2 = ? WHERE id = ?", (formatted, row[0]))
    else:
        cur.execute("UPDATE members_contact SET phone1 = ? WHERE id = ?", (formatted, row[0]))
    return True


def main():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    updated = 0
    skipped = 0

    # Process checkouts
    rows = cur.execute(
        "SELECT member_number, phone FROM checkouts WHERE phone IS NOT NULL AND phone != '' ORDER BY id ASC"
    ).fetchall()
    for member_number, phone in rows:
        if sync_phone(cur, member_number, phone):
            updated += 1
        else:
            skipped += 1

    # Process restrings
    rows = cur.execute(
        "SELECT member_number, phone FROM restrings WHERE phone IS NOT NULL AND phone != '' ORDER BY id ASC"
    ).fetchall()
    for member_number, phone in rows:
        if sync_phone(cur, member_number, phone):
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    print(f"Done.")
    print(f"  Phone fields updated: {updated}")
    print(f"  Skipped (no match / already on file): {skipped}")


if __name__ == '__main__':
    main()
