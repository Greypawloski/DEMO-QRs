"""
One-time fix: merge all variations of Justin's name into "Justin Cuellar".
Run from /home/SACCTennis/DEMO-QRs/:
    python merge_stringer_name.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.execute(
    "UPDATE restrings SET strung_by = 'Justin' WHERE LOWER(strung_by) LIKE '%justin%'"
)
justin_count = cur.rowcount

cur.execute(
    "UPDATE restrings SET strung_by = 'John' WHERE LOWER(strung_by) LIKE '%john%' OR LOWER(strung_by) LIKE '%joihn%'"
)
john_count = cur.rowcount

conn.commit()
conn.close()

print(f"Done.")
print(f"  Justin: {justin_count} record(s) updated.")
print(f"  John:   {john_count} record(s) updated.")
