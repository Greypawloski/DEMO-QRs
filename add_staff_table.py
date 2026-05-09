"""
Migration: create staff table and import existing STAFF_NAMES env var.
Run once on PythonAnywhere: python add_staff_table.py
"""
import sqlite3, os

DB_PATH = os.environ.get("DB_PATH", "demo.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS staff (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
""")

existing_names = [n.strip() for n in os.environ.get("STAFF_NAMES", "").split(",") if n.strip()]
for name in existing_names:
    try:
        c.execute("INSERT INTO staff (name) VALUES (?)", (name,))
        print(f"Imported: {name}")
    except sqlite3.IntegrityError:
        print(f"Already exists: {name}")

conn.commit()
conn.close()
print("Done.")
