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
    "UPDATE restrings SET strung_by = 'Justin Cuellar' WHERE LOWER(strung_by) LIKE '%justin%'"
)
updated = cur.rowcount
conn.commit()
conn.close()

print(f"Done. Updated {updated} record(s) to 'Justin Cuellar'.")
