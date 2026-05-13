"""Migration: add picked_up_at column to restrings table."""
import sqlite3, os

DB_PATH = os.environ.get('DB_PATH', 'demo.db')

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

cols = [row[1] for row in cur.execute("PRAGMA table_info(restrings)").fetchall()]
if 'picked_up_at' not in cols:
    cur.execute("ALTER TABLE restrings ADD COLUMN picked_up_at TEXT")
    print("Added picked_up_at column.")
else:
    print("picked_up_at already exists, skipping.")

con.commit()
con.close()
