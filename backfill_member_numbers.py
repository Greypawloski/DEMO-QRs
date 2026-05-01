"""
One-time script: match restring records that have no member_number against
the members directory by name, and fill in the member_number when exactly
one match is found.

Name matching handles two formats:
  - "Last, First"  stored in members  vs  "First Last" stored in restrings
  - exact match (same format in both)

Only updates when exactly ONE member matches — skips ambiguous common names.

Run from /home/SACCTennis/DEMO-QRs/:
    python backfill_member_numbers.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'


def normalize(name):
    """Return lowercase stripped name."""
    return (name or '').strip().lower()


def name_variants(raw):
    """
    Given a stored customer_name, return candidate member_name values to try.
    Handles both 'First Last' and 'Last, First' input.
    """
    raw = raw.strip()
    variants = [normalize(raw)]

    if ',' in raw:
        # Already "Last, First" — also try "First Last"
        parts = [p.strip() for p in raw.split(',', 1)]
        if len(parts) == 2 and parts[1]:
            variants.append(normalize(f'{parts[1]} {parts[0]}'))
    else:
        # "First Last..." — also try "Last, First"
        tokens = raw.split()
        if len(tokens) >= 2:
            first = tokens[0]
            last  = ' '.join(tokens[1:])
            variants.append(normalize(f'{last}, {first}'))

    return list(dict.fromkeys(variants))  # deduplicate, preserve order


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    unlinked = cur.execute(
        "SELECT id, customer_name FROM restrings WHERE member_number IS NULL OR member_number = ''"
    ).fetchall()

    updated           = 0
    skipped_ambiguous = 0
    skipped_no_match  = 0

    debug_names = {'crain canavan', 'rossi lee', 'james williams'}

    for row in unlinked:
        variants = name_variants(row['customer_name'])

        if normalize(row['customer_name']) in debug_names:
            print(f"DEBUG '{row['customer_name']}' variants: {variants}")

        matches = []
        for v in variants:
            hits = cur.execute(
                "SELECT member_number FROM members_contact WHERE LOWER(member_name) = ?", (v,)
            ).fetchall()
            for h in hits:
                mn = h['member_number']
                if mn not in matches:
                    matches.append(mn)

        if normalize(row['customer_name']) in debug_names:
            print(f"  → matches: {matches}")

        if len(matches) == 1:
            cur.execute(
                "UPDATE restrings SET member_number = ? WHERE id = ?",
                (matches[0], row['id'])
            )
            updated += 1
        elif len(matches) > 1:
            print(f"  AMBIGUOUS '{row['customer_name']}' → {matches}")
            skipped_ambiguous += 1
        else:
            skipped_no_match += 1

    conn.commit()
    conn.close()

    print(f"\nDone.")
    print(f"  Updated:             {updated}")
    print(f"  No match found:      {skipped_no_match}")
    print(f"  Ambiguous (skipped): {skipped_ambiguous}")


if __name__ == '__main__':
    main()
