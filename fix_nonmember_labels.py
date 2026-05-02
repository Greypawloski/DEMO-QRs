"""
Migration: ensure specific non-member customers have member_number = 'Non-member'
in the restrings table so they appear in non-member search and history dropdowns.

Run from the project root on PythonAnywhere:
    python fix_nonmember_labels.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'

# Names to normalise — case-insensitive search, exact customer_name preserved
NAMES = [
    'Samuel Montemayor',
    'Sergio Montemayor',
    'Jon Weigand',
    'Ben Rhame',
    'Kate Winslow',
    'Ally Winslow',
    'Allyson Winslow',
    'Jack Winslow',
    'Reagan Winslow',
    'Elle Winslow',
]

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

total_updated = 0

for name in NAMES:
    rows = conn.execute(
        "SELECT id, customer_name, member_number, racquet, date_in FROM restrings "
        "WHERE LOWER(customer_name) = LOWER(?)",
        (name,)
    ).fetchall()

    if not rows:
        print(f"  NOT FOUND: {name}")
        continue

    needs_fix = [r for r in rows if r['member_number'] != 'Non-member']
    already_ok = [r for r in rows if r['member_number'] == 'Non-member']

    print(f"\n{name}  ({len(rows)} total restring(s), {len(already_ok)} already correct)")
    for r in rows:
        flag = '' if r['member_number'] == 'Non-member' else '  ← will fix'
        print(f"   id={r['id']}  member_number={r['member_number']!r}  racquet={r['racquet']!r}  date={r['date_in']}{flag}")

    if needs_fix:
        ids = [r['id'] for r in needs_fix]
        placeholders = ','.join('?' * len(ids))
        conn.execute(
            f"UPDATE restrings SET member_number = 'Non-member' WHERE id IN ({placeholders})",
            ids
        )
        total_updated += len(ids)

conn.commit()
conn.close()

print(f"\nDone. Updated {total_updated} restring record(s) to member_number = 'Non-member'.")
