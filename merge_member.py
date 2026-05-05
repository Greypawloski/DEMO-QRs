"""
One-time script: merge restring (and checkout) history for
  "Frederick Thompson" / member #3870
into the canonical directory entry
  "Thomson IV, Frederick"

Run from the PythonAnywhere bash console:
  cd ~/DEMO-QRs && python merge_member.py

The script prints a dry-run summary first and asks for confirmation.
"""

import os, sys, sqlite3

DB_PATH = os.environ.get("DB_PATH", "demo.db")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row


# ── 1. Locate the two sides ──────────────────────────────────────────────────

# Source: whatever is stored under "Frederick Thompson" / #3870
src_restrings = db.execute("""
    SELECT id, customer_name, member_number, racquet, string, date_in
    FROM restrings
    WHERE member_number = '3870'
       OR (LOWER(customer_name) LIKE '%frederick%' AND LOWER(customer_name) LIKE '%thompson%')
    ORDER BY id
""").fetchall()

src_checkouts = db.execute("""
    SELECT id, customer_name, member_number, equipment_id, checked_out_at
    FROM checkouts
    WHERE member_number = '3870'
       OR (LOWER(customer_name) LIKE '%frederick%' AND LOWER(customer_name) LIKE '%thompson%')
    ORDER BY id
""").fetchall()

# Target directory entry
target_dir = db.execute("""
    SELECT id, member_name, member_number, phone1, email1
    FROM members_contact
    WHERE LOWER(member_name) LIKE '%thomson%'
      AND LOWER(member_name) LIKE '%frederick%'
""").fetchall()

# Also check if #3870 is already in members_contact
src_dir = db.execute("""
    SELECT id, member_name, member_number, phone1, email1
    FROM members_contact
    WHERE member_number = '3870'
""").fetchall()


# ── 2. Print dry-run summary ─────────────────────────────────────────────────

print("\n── SOURCE: restring records ──")
if src_restrings:
    for r in src_restrings:
        print(f"  #{r['id']}  {r['date_in']}  {r['customer_name']}  m#{r['member_number']}  {r['racquet']}")
else:
    print("  (none found)")

print("\n── SOURCE: checkout records ──")
if src_checkouts:
    for c in src_checkouts:
        print(f"  #{c['id']}  {c['checked_out_at']}  {c['customer_name']}  m#{c['member_number']}")
else:
    print("  (none found)")

print("\n── members_contact #3870 ──")
for r in src_dir:
    print(f"  id={r['id']}  name='{r['member_name']}'  num={r['member_number']}  phone={r['phone1']}  email={r['email1']}")

print("\n── members_contact Thomson IV, Frederick ──")
for r in target_dir:
    print(f"  id={r['id']}  name='{r['member_name']}'  num={r['member_number']}  phone={r['phone1']}  email={r['email1']}")

if not target_dir:
    print("  ERROR: 'Thomson IV, Frederick' not found in members_contact.")
    print("  Check spelling or look up the entry manually.")
    sys.exit(1)

if len(target_dir) > 1:
    print("  WARNING: multiple matches. Using first entry.")

target = target_dir[0]
canonical_name   = target['member_name']    # e.g. "Thomson IV, Frederick"
canonical_number = target['member_number']  # the authoritative member number

print(f"\n── PLAN ──")
print(f"  Canonical member : '{canonical_name}'  #{canonical_number}")
print(f"  Restrings to update : {len(src_restrings)}")
print(f"  Checkouts to update : {len(src_checkouts)}")

# Determine display name (First Last format) for customer_name field
parts = canonical_name.split(',')
display_name = (parts[1].strip() + ' ' + parts[0].strip()) if len(parts) == 2 else canonical_name
print(f"  customer_name will be set to : '{display_name}'")

# Warn if a separate members_contact row for #3870 exists and differs from target
stale_dir_rows = [r for r in src_dir if r['id'] != target['id']]
if stale_dir_rows:
    print(f"\n  NOTE: members_contact also has a row for #3870 (id={stale_dir_rows[0]['id']},")
    print(f"  name='{stale_dir_rows[0]['member_name']}'). That row will be deleted after merge.")

if not src_restrings and not src_checkouts:
    print("\n  Nothing to update — no matching restring or checkout records found.")
    sys.exit(0)

print()
answer = input("Apply these changes? [yes/no]: ").strip().lower()
if answer != 'yes':
    print("Aborted — no changes made.")
    sys.exit(0)


# ── 3. Apply ─────────────────────────────────────────────────────────────────

db.execute("BEGIN")

# Update restrings
if src_restrings:
    db.execute("""
        UPDATE restrings
        SET customer_name = ?, member_number = ?
        WHERE member_number = '3870'
           OR (LOWER(customer_name) LIKE '%frederick%' AND LOWER(customer_name) LIKE '%thompson%')
    """, (display_name, canonical_number))
    print(f"  Updated {db.execute('SELECT changes()').fetchone()[0]} restring row(s).")

# Update checkouts
if src_checkouts:
    db.execute("""
        UPDATE checkouts
        SET customer_name = ?, member_number = ?
        WHERE member_number = '3870'
           OR (LOWER(customer_name) LIKE '%frederick%' AND LOWER(customer_name) LIKE '%thompson%')
    """, (display_name, canonical_number))
    print(f"  Updated {db.execute('SELECT changes()').fetchone()[0]} checkout row(s).")

# Remove stale members_contact row for #3870 if it differs from the canonical target
for stale in stale_dir_rows:
    db.execute("DELETE FROM members_contact WHERE id = ?", (stale['id'],))
    print(f"  Deleted stale members_contact row id={stale['id']} ('{stale['member_name']}').")

# Also ensure #3870 in members_contact points to the canonical entry
# (update canonical row's member_number if it was different)
if canonical_number != '3870':
    confirm2 = input(
        f"\n  The canonical directory entry has member_number='{canonical_number}', not '3870'.\n"
        f"  Should restring/checkout records use '{canonical_number}'? (already applied above)\n"
        f"  Also update members_contact id={target['id']} to member_number='3870'? [yes/no]: "
    ).strip().lower()
    if confirm2 == 'yes':
        db.execute("UPDATE members_contact SET member_number='3870' WHERE id=?", (target['id'],))
        print(f"  Updated members_contact member_number to '3870'.")

db.execute("COMMIT")
print("\nDone. Run the app and verify the restring list for Frederick Thomson IV.")
