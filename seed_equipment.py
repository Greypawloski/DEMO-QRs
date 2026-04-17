"""
Run this once in the PythonAnywhere Bash console to bulk-insert all demo racquets:
    cd ~/DEMO-QRs && python seed_equipment.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from database import get_db
from qr_utils import generate_qr

RACQUETS = [
    # (name, head_size, grip_size, weight_g, string_pattern)
    ("Yonex V-core 95 v7",               "95",  "4 1/2 inch", "310", "16x20"),
    ("Yonex V-core 100L v7",             "100", "4 1/2 inch", "280", "16x19"),
    ("Yonex V-core 100 v7",              "100", "4 1/2 inch", "300", "16x19"),
    ("Yonex V-core 98 v7",               "98",  "4 1/2 inch", "305", "16x19"),
    ("Head Boom MP (2024)",               "100", "4 1/2 inch", "295", "16x19"),
    ("Head Squared",                      "100", "4 1/2 inch", "295", "16x18"),
    ("Head Boom MP",                      "100", "4 1/2 inch", "295", "16x19"),
    ("Head Graphene 360+ Speed Lite",     "100", "4 1/2 inch", "265", "16x19"),
    ("Head Graphene 360+ Speed S",        "100", "4 1/2 inch", "285", "16x19"),
    ("Head Gravity Team",                 "104", "4 1/2 inch", "270", "16x20"),
    ("Head Extreme MP (2024)",            "100", "4 1/2 inch", "300", "16x19"),
    ("Tecnifibre TF-X1 300",             "100", "4 1/2 inch", "300", "16x19"),
    ("Tecnifibre TF-X1 275 (105)",       "105", "4 1/2 inch", "275", "16x19"),
    ("Tecnifibre TF-X1 285",             "100", "4 1/2 inch", "285", "16x19"),
    ("Wilson Blade 100L v9",             "100", "4 1/2 inch", "285", "16x19"),
    ("Wilson Blade 98 v9 16x19",         "98",  "4 1/2 inch", "305", "16x19"),
    ("Wilson Blade 98 v9 18x20",         "98",  "4 1/2 inch", "305", "18x20"),
    ("Wilson Burn 100LS v5",             "100", "4 1/2 inch", "280", "18x16"),
    ("Wilson Burn 100 v5",               "100", "4 1/2 inch", "300", "16x19"),
    ("Wilson Burn 100 ULS",              "100", "4 1/2 inch", "260", "18x16"),
    ("Babolat Pure Aero",                "100", "4 1/2 inch", "300", "16x19"),
    ("Tecnifibre T-Fight 285",           "100", "4 1/2 inch", "285", "16x19"),
    ("Tecnifibre T-Fight 300 (A)",       "100", "4 1/2 inch", "300", "16x19"),
    ("Tecnifibre T-Fight 300 (B)",       "100", "4 1/2 inch", "300", "16x19"),
    ("Babolat Pure Strike 97",           "97",  "4 1/2 inch", "310", "16x20"),
    ("Babolat Pure Strike 100",          "100", "4 1/2 inch", "300", "16x19"),
    ("Tecnifibre TF-X1 305",             "98",  "4 1/2 inch", "305", "16x19"),
    ("Tecnifibre TF-X1 275 (98)",        "105", "4 1/2 inch", "275", "16x19"),
    ("Tecnifibre T-Fight 315",           "98",  "4 1/2 inch", "315", "16x19"),
    ("Tecnifibre T-Fight 305",           "98",  "4 1/2 inch", "305", "18x19"),
    ("Babolat Pure Drive 98",            "98",  "4 1/2 inch", "305", "16x20"),
    ("Babolat Pure Drive 107",           "107", "4 1/2 inch", "285", "16x19"),
    ("Babolat Pure Drive",               "100", "4 1/2 inch", "300", "16x19"),
    ("Babolat Pure Drive Team",          "100", "4 1/2 inch", "285", "16x19"),
    ("Babolat Pure Drive+",              "100", "4 1/2 inch", "300", "16x19"),
    ("Yonex Ezone 100 (A)",              "100", "4 1/2 inch", "300", "16x19"),
    ("Yonex Ezone 98",                   "98",  "4 1/2 inch", "305", "16x19"),
    ("Yonex Ezone 105",                  "105", "4 1/2 inch", "275", "16x19"),
    ("Head Instinct MP",                 "100", "4 1/2 inch", "300", "16x19"),
    ("Yonex Ezone 100 (B)",              "100", "4 1/2 inch", "300", "16x19"),
    ("Yonex Ezone 115",                  "115", "4 1/2 inch", "250", "16x18"),
    ("Head Radical MP",                  "98",  "4 1/2 inch", "300", "16x19"),
    ("Head Radical Team",                "102", "4 1/2 inch", "280", "16x19"),
    ("Yonex Ezone 100L",                 "100", "4 1/2 inch", "285", "16x19"),
    ("Yonex Ezone 110",                  "110", "4 1/2 inch", "255", "16x18"),
    ("Wilson Clash 100 v3",              "100", "4 1/2 inch", "295", "16x19"),
    ("Wilson Clash 100L v3",             "100", "4 1/2 inch", "280", "16x19"),
    ("Wilson Clash 108 v3",              "108", "4 1/2 inch", "280", "16x19"),
    ("Wilson Ultra 99 Pro v5",           "99",  "4 1/2 inch", "305", "16x18"),
    ("Wilson Ultra 100 v5",              "100", "4 1/2 inch", "300", "16x19"),
    ("Wilson Ultra 100L v5",             "100", "4 1/2 inch", "280", "16x19"),
    ("Wilson Ultra 100UL v5",            "100", "4 1/2 inch", "260", "16x19"),
    ("Wilson Ultra 111 v5",              "111", "4 1/2 inch", "270", "16x18"),
    ("Head Boom (2026)",                 "100", "4 1/2 inch", "295", "16x19"),
    ("Babolat Pure Aero Lite (2026)",    "100", "4 1/2 inch", "270", "16x19"),
    ("Babolat Pure Aero Team (2026)",    "100", "4 1/2 inch", "285", "16x19"),
    ("Babolat Pure Aero (2026)",         "100", "4 1/2 inch", "300", "16x19"),
    ("Babolat Pure Aero 98 (2026)",      "98",  "4 1/2 inch", "305", "16x20"),
]

app = create_app()
with app.app_context():
    db = get_db()
    inserted = 0
    for name, head, grip, weight, pattern in RACQUETS:
        cur = db.execute(
            """
            INSERT INTO equipment
              (name, category,
               spec1_label, spec1_value,
               spec2_label, spec2_value,
               spec3_label, spec3_value,
               spec4_label, spec4_value)
            VALUES (?, 'racquet', 'Head Size', ?, 'Grip Size', ?, 'Weight (unstrung)', ?, 'String Pattern', ?)
            """,
            (name, f"{head} sq in", grip, f"{weight} g", pattern)
        )
        equipment_id = cur.lastrowid
        filename = generate_qr(equipment_id, app.config['QR_BASE_URL'])
        db.execute("UPDATE equipment SET qr_filename=? WHERE id=?", (filename, equipment_id))
        inserted += 1
        print(f"  [{inserted}/58] {name}")
    db.commit()
    print(f"\nDone — {inserted} racquets added.")
