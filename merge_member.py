"""
One-time script: set member_number = '3870' on all restring (and checkout)
records where customer_name is "Frederick Thomson".

Run from the PythonAnywhere bash console:
  cd ~/DEMO-QRs && python merge_member.py
"""

import os, sys, sqlite3

DB_PATH = os.environ.get("DB_PATH", "demo.db")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row

NAME_FILTER = (
    "LOWER(customer_name) LIKE '%frederick%' AND LOWER(customer_name) LIKE '%thomson%'"
)

restrings = db.execute(
    f"SELECT id, customer_name, member_number, racquet, date_in FROM restrings WHERE {NAME_FILTER} ORDER BY id"
).fetchall()

checkouts = db.execute(
    f"SELECT id, customer_name, member_number, checked_out_at FROM checkouts WHERE {NAME_FILTER} ORDER BY id"
).fetchall()

print("\n── Restrings found ──")
if restrings:
    for r in restrings:
        print(f"  #{r['id']}  {r['date_in']}  '{r['customer_name']}'  current member#={r['member_number']}  {r['racquet']}")
else:
    print("  (none)")

print("\n── Checkouts found ──")
if checkouts:
    for c in checkouts:
        print(f"  #{c['id']}  {c['checked_out_at']}  '{c['customer_name']}'  current member#={c['member_number']}")
else:
    print("  (none)")

if not restrings and not checkouts:
    print("\nNothing to update.")
    sys.exit(0)

print(f"\nWill set member_number = '3870' on {len(restrings)} restring(s) and {len(checkouts)} checkout(s).")
answer = input("Apply? [yes/no]: ").strip().lower()
if answer != 'yes':
    print("Aborted.")
    sys.exit(0)

db.execute(f"UPDATE restrings SET member_number='3870' WHERE {NAME_FILTER}")
db.execute(f"UPDATE checkouts SET member_number='3870' WHERE {NAME_FILTER}")
db.commit()
print("Done.")
