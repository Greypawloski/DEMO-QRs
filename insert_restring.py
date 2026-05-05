"""
One-time script: insert Ann Cross restring record into history.
Run on PythonAnywhere: python insert_restring.py
"""
import sqlite3, os, sys

DB_PATH = os.environ.get("DB_PATH", "demo.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
    INSERT INTO restrings
        (date_in, customer_name, phone, member_number, racquet, string, tension,
         date_promised, receipt, strung_by, status, completed_at, no_sms, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
""", (
    '2026-04-01',           # date_in
    'Ann Cross',            # customer_name
    '',                     # phone (not provided for manual entry)
    None,                   # member_number
    'Yonex Vcore 100',      # racquet
    'Tecnifibre Triax 16',  # string
    '54',                   # tension
    '2026-04-01',           # date_promised
    '12321542',             # receipt / chit #
    'Marco',                # strung_by
    'picked_up',            # status — historical completed entry
    '2026-04-01 00:00:00',  # completed_at
    1,                      # no_sms
))

conn.commit()
inserted_id = c.lastrowid
conn.close()

print(f"Inserted restring record id={inserted_id} for Ann Cross.")
