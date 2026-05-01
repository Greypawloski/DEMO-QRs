"""
Manual name → member number backfill for known nickname/spelling variants.
Only updates records where member_number is currently blank.

Run from /home/SACCTennis/DEMO-QRs/:
    python manual_backfill_members.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'


def main():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    def update(names, member_number, racquet_contains=None):
        count = 0
        for name in names:
            if racquet_contains:
                cur.execute(
                    """UPDATE restrings SET member_number=?
                       WHERE (member_number IS NULL OR member_number='')
                         AND LOWER(customer_name)=?
                         AND LOWER(racquet) LIKE ?""",
                    (member_number, name.lower(), f'%{racquet_contains.lower()}%')
                )
            else:
                cur.execute(
                    """UPDATE restrings SET member_number=?
                       WHERE (member_number IS NULL OR member_number='')
                         AND LOWER(customer_name)=?""",
                    (member_number, name.lower())
                )
            count += cur.rowcount
        return count

    results = [
        update(['Ray Welder'],                                          '4818'),
        update(['Will Thompson', 'William Thompson'],                   '4605A'),
        update(['James Williams'],                                      '3349',   racquet_contains='tecnifibre'),
        update(['Peter McLaughlin', 'Peter Mclaughlin'],               '4454'),
        update(['Emily Jones'],                                         '4881A'),
        update(['John Moorman'],                                        '4522'),
        update(['Phillip Cooney', 'Phil Cooney', 'Philip Cooney'],     '4786A'),
        update(['Rossi Lee'],                                           '5411B'),  # also has 4123B (two parents)
    ]

    conn.commit()
    conn.close()

    labels = [
        'Ray Welder       → 4818',
        'Thompson         → 4605A',
        'James Williams   → 3349 (Tecnifibre only)',
        'Peter McLaughlin → 4454',
        'Emily Jones      → 4881A',
        'John Moorman     → 4522',
        'Phil(lip) Cooney → 4786A',
        'Rossi Lee        → 5411B',
    ]
    print("Done.")
    for label, count in zip(labels, results):
        print(f"  {label}: {count} record(s)")
    print(f"\n  Total updated: {sum(results)}")


if __name__ == '__main__':
    main()
