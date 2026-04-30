"""
Scheduled task: send a reminder SMS for restrings that have been marked
ready for pickup for over 72 hours and haven't been reminded yet.

Set up as a PythonAnywhere scheduled task to run daily (or every few hours).

Run manually from /home/SACCTennis/DEMO-QRs/:
    python send_restring_reminders.py
"""

import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / 'demo.db'

# How long after marking ready before sending reminder
REMINDER_AFTER_HOURS = 72


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=REMINDER_AFTER_HOURS)
    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')

    due = cur.execute(
        """
        SELECT id, customer_name, phone
        FROM restrings
        WHERE status = 'complete'
          AND no_sms = 0
          AND reminded_at IS NULL
          AND phone IS NOT NULL AND phone != ''
          AND completed_at IS NOT NULL
          AND completed_at <= ?
        """,
        (cutoff_str,)
    ).fetchall()

    if not due:
        print("No reminders to send.")
        conn.close()
        return

    sys.path.insert(0, str(Path(__file__).parent))
    from sms import send_sms

    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    sent = 0
    for row in due:
        first_name = row['customer_name'].split()[0]
        send_sms(
            row['phone'],
            f"Hi {first_name}, just a reminder that your racquet is still ready for pickup at the SACC Tennis Shop. "
            f"Please stop by during business hours. Reply STOP to opt out."
        )
        cur.execute(
            "UPDATE restrings SET reminded_at = ? WHERE id = ?",
            (now_str, row['id'])
        )
        print(f"  Reminder sent to {row['customer_name']} ({row['phone']})")
        sent += 1

    conn.commit()
    conn.close()
    print(f"Done. {sent} reminder(s) sent.")


if __name__ == '__main__':
    main()
