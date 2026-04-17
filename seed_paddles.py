"""
Run once in PythonAnywhere Bash console to add demo paddles:
    cd ~/DEMO-QRs && python seed_paddles.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from database import get_db
from qr_utils import generate_qr

PADDLES = [
    "Engage Evolution Aero",
    "Engage Pursuit v2.0",
    "Engage Pursuit MX Pro",
    "Engage Pursuit Pro1 6.0 (Copy 1)",
    "Engage Pursuit EX 6.0 Pro",
    "Engage Pursuit EX Pro",
    "Engage Pursuit Pro1 6.0 (Copy 2)",
]

app = create_app()
with app.app_context():
    db = get_db()
    inserted = 0
    for name in PADDLES:
        cur = db.execute(
            """
            INSERT INTO equipment
              (name, category,
               spec1_label, spec2_label, spec3_label, spec4_label, spec5_label)
            VALUES (?, 'paddle', 'Surface', 'Core', 'Thickness', 'Grip Size', 'Weight')
            """,
            (name,)
        )
        equipment_id = cur.lastrowid
        filename = generate_qr(equipment_id, app.config['QR_BASE_URL'])
        db.execute("UPDATE equipment SET qr_filename=? WHERE id=?", (filename, equipment_id))
        inserted += 1
        print(f"  [{inserted}/{len(PADDLES)}] {name}")
    db.commit()
    print(f"\nDone — {inserted} paddles added.")
