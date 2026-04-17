from app import create_app
from database import get_db

app = create_app()
with app.app_context():
    db = get_db()
    result = db.execute(
        "UPDATE equipment SET spec2_value='4 1/4 inch' WHERE spec2_label='Grip Size'"
    )
    db.commit()
    print(f"Updated {result.rowcount} racquets.")
