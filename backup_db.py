"""
Automated SQLite backup — safe online backup using SQLite's built-in API.
Keeps the 14 most recent daily backups and deletes older ones automatically.

Schedule on PythonAnywhere (Daily Tasks tab):
    python /home/SACCTennis/DEMO-QRs/backup_db.py

Backups land in:  /home/SACCTennis/DEMO-QRs/backups/
"""
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH     = Path('/home/SACCTennis/DEMO-QRs/demo.db')
BACKUP_DIR  = Path('/home/SACCTennis/DEMO-QRs/backups')
KEEP_DAYS   = 14

def main():
    BACKUP_DIR.mkdir(exist_ok=True)

    timestamp   = datetime.now().strftime('%Y-%m-%d_%H%M')
    backup_path = BACKUP_DIR / f'demo_{timestamp}.db'

    # SQLite online backup — safe even while the app is running
    src  = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(backup_path)
    src.backup(dest)
    dest.close()
    src.close()

    size_kb = backup_path.stat().st_size // 1024
    print(f"Backup saved: {backup_path.name}  ({size_kb} KB)")

    # Prune oldest backups beyond KEEP_DAYS
    backups = sorted(BACKUP_DIR.glob('demo_*.db'))
    for old in backups[:-KEEP_DAYS]:
        old.unlink()
        print(f"Deleted old backup: {old.name}")

if __name__ == '__main__':
    main()
