"""
One-time script: create the strings_stock table and load from tennis_strings_chart.pdf.
Run on PythonAnywhere:  cd ~/DEMO-QRs && python import_strings.py
"""
import os, sqlite3

DB_PATH = os.environ.get("DB_PATH", "demo.db")
db = sqlite3.connect(DB_PATH)

db.execute("""
    CREATE TABLE IF NOT EXISTS strings_stock (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        brand       TEXT NOT NULL,
        model       TEXT NOT NULL,
        string_type TEXT,
        color       TEXT,
        gauges      TEXT
    )
""")
db.execute("DELETE FROM strings_stock")  # clear before re-import

STRINGS = [
    ("Babolat",      "RPM Blast",            "Polyester (Poly)",      "Black",                    "17g"),
    ("Babolat",      "Xcel Comfort Power",   "Multifilament",         "White",                    "16g, 17g"),
    ("Babolat",      "Xplore",               "Multifilament",         "Blue",                     "16g"),
    ("Head",         "Synthetic Gut",        "Synthetic Gut",         "White/Black/Red/Yellow/Blue","16g, 17g"),
    ("Head",         "Velocity MLT",         "Multifilament",         "White",                    "16g, 17g"),
    ("Solinco",      "Hyper-G",              "Polyester (Poly)",      "Green",                    "16L"),
    ("Solinco",      "Tour Bite",            "Polyester (Poly)",      "Black",                    "16L"),
    ("Technifibre",  "Black Code",           "Polyester (Poly)",      "Black",                    "16g"),
    ("Technifibre",  "NRG2",                 "Multifilament",         "White",                    "16g"),
    ("Technifibre",  "Razor Soft",           "Polyester (Poly)",      "White",                    "16g"),
    ("Technifibre",  "Triax",                "Hybrid (Poly/Multi)",   "White",                    "16g"),
    ("Wilson",       "NXT",                  "Multifilament",         "White/Black",              "16g, 17g"),
    ("Wilson",       "NXT OS",               "Multifilament",         "White",                    "16L"),
    ("Wilson",       "NXT Soft",             "Multifilament",         "Gray",                     "16g"),
    ("Wilson",       "Sensation",            "Multifilament",         "White",                    "15g, 16g, 17g"),
    ("Wilson",       "Synthetic Gut Power",  "Synthetic Gut",         "White/Black",              "16g, 17g"),
    ("Yonex",        "Rexis Comfort",        "Multifilament",         "White",                    "16g, 16L"),
    ("Yonex",        "Rexis Speed",          "Multifilament",         "White",                    "16g"),
]

db.executemany(
    "INSERT INTO strings_stock (brand, model, string_type, color, gauges) VALUES (?,?,?,?,?)",
    STRINGS
)
db.commit()
print(f"Imported {len(STRINGS)} strings into strings_stock table.")
