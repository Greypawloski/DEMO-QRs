"""
Import historical restring records from CSV files exported from Numbers.

- Place all CSV files in /home/SACCTennis/DEMO-QRs/string_history_import/
- Run from /home/SACCTennis/DEMO-QRs/:
      python import_string_history.py
- Safe to re-run: skips rows that already exist (matched on name + date + racquet + string)

Expected CSV columns (in any order):
  Name, Racquet, String, Tension, Stringer, Date, Chit Number, Total, Additional Charges
"""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH     = Path(__file__).parent / 'demo.db'
IMPORT_DIR  = Path(__file__).parent / 'string_history_import'


def parse_date(raw):
    """Parse M/D/YY or M/D/YYYY into YYYY-MM-DD. Returns None if unparseable."""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ('%m/%d/%y', '%m/%d/%Y'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def clean(val):
    return val.strip() if val else ''


def main():
    if not IMPORT_DIR.exists():
        print(f"ERROR: Import folder not found: {IMPORT_DIR}")
        print("Create the folder and place your CSV files inside it, then re-run.")
        return

    csv_files = sorted(IMPORT_DIR.glob('*.csv'))
    if not csv_files:
        print(f"No CSV files found in {IMPORT_DIR}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    total_inserted = 0
    total_skipped  = 0
    total_errors   = 0

    for csv_path in csv_files:
        print(f"\nProcessing: {csv_path.name}")
        inserted = skipped = errors = 0

        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            # Normalize headers (strip whitespace)
            reader.fieldnames = [h.strip() for h in reader.fieldnames] if reader.fieldnames else []

            for row in reader:
                name    = clean(row.get('Name', ''))
                racquet = clean(row.get('Racquet', ''))
                string  = clean(row.get('String', ''))
                tension = clean(row.get('Tension', ''))
                stringer= clean(row.get('Stringer', ''))
                date_raw= clean(row.get('Date', ''))
                receipt = clean(row.get('Chit Number', ''))
                charged = clean(row.get('Total', ''))
                add_chg = clean(row.get('Additional Charges', ''))

                # Skip completely empty rows
                if not name and not racquet:
                    continue

                date_in = parse_date(date_raw)
                if not date_in:
                    print(f"  SKIP (bad date '{date_raw}'): {name} — {racquet}")
                    errors += 1
                    continue

                # Deduplicate: skip if same name + date + racquet + string already exists
                exists = cur.execute(
                    """SELECT id FROM restrings
                       WHERE customer_name=? AND date_in=? AND racquet=? AND string=?""",
                    (name, date_in, racquet, string)
                ).fetchone()
                if exists:
                    skipped += 1
                    continue

                try:
                    cur.execute(
                        """INSERT INTO restrings
                             (date_in, customer_name, phone, member_number, racquet,
                              string, tension, date_promised, receipt, charged,
                              additional_charges, strung_by, status, completed_at,
                              no_sms, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            date_in,
                            name,
                            '',          # phone — not in historical data
                            '',          # member_number — not in historical data
                            racquet,
                            string,
                            tension,
                            date_in,     # date_promised — use date_in as best guess
                            receipt,
                            charged,
                            add_chg,
                            stringer,
                            'picked_up', # all historical = completed
                            date_in,     # completed_at
                            1,           # no_sms — never send SMS for historical records
                            date_in,     # created_at
                        )
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  ERROR inserting {name} — {racquet}: {e}")
                    errors += 1

        conn.commit()
        print(f"  Inserted: {inserted}  Skipped (duplicate): {skipped}  Errors: {errors}")
        total_inserted += inserted
        total_skipped  += skipped
        total_errors   += errors

    conn.close()
    print(f"\nAll done.")
    print(f"  Total inserted: {total_inserted}")
    print(f"  Total skipped:  {total_skipped}")
    print(f"  Total errors:   {total_errors}")


if __name__ == '__main__':
    main()
