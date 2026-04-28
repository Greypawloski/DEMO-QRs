from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from PIL import Image as PILImage
import config
from database import get_db, init_db, init_app as db_init_app
from auth import auth_bp
from admin import admin_bp
from restrings import restrings_bp

CENTRAL = ZoneInfo('America/Chicago')


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['ADMIN_PASSWORD'] = config.ADMIN_PASSWORD
    app.config['DB_PATH'] = config.DB_PATH
    app.config['QR_BASE_URL'] = config.QR_BASE_URL
    app.config['RETIRE_PIN']   = config.RETIRE_PIN
    app.config['STAFF_NAMES']  = config.STAFF_NAMES

    @app.template_filter('central')
    def to_central(dt_str):
        if not dt_str:
            return '—'
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=ZoneInfo('UTC'))
        return dt.astimezone(CENTRAL).strftime('%-m/%-d/%Y %-I:%M %p')

    db_init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(restrings_bp)

    # Auto-initialize DB on first request if it doesn't exist
    @app.before_request
    def ensure_db():
        import os
        if not os.path.exists(app.config['DB_PATH']):
            with app.app_context():
                init_db()

    @app.route('/')
    def home():
        db = get_db()
        rows = db.execute(
            """
            SELECT e.name, e.category, e.under_maintenance,
                   e.spec1_label, e.spec1_value, e.spec2_label, e.spec2_value,
                   e.spec3_label, e.spec3_value, e.spec4_label, e.spec4_value,
                   e.spec5_label, e.spec5_value,
                   CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END AS is_checked_out
            FROM equipment e
            LEFT JOIN checkouts c ON e.id = c.equipment_id AND c.returned_at IS NULL
            WHERE e.active = 1
            ORDER BY e.category, e.name
            """
        ).fetchall()
        racquets = [r for r in rows if r['category'] == 'racquet']
        paddles  = [r for r in rows if r['category'] == 'paddle']
        return render_template('demos.html', racquets=racquets, paddles=paddles)

    @app.route('/checkout/<int:equipment_id>', methods=['GET', 'POST'])
    def checkout(equipment_id):
        db = get_db()
        item = db.execute(
            "SELECT * FROM equipment WHERE id = ? AND active = 1", (equipment_id,)
        ).fetchone()
        if item is None:
            return render_template('errors/404.html'), 404

        # Check if already checked out (inside transaction for safety)
        existing = db.execute(
            "SELECT id FROM checkouts WHERE equipment_id = ? AND returned_at IS NULL",
            (equipment_id,)
        ).fetchone()

        if request.method == 'POST':
            if existing:
                return redirect(url_for('checkout_unavailable', equipment_id=equipment_id))
            name = request.form.get('customer_name', '').strip()
            non_member = request.form.get('non_member') == '1'
            member = 'Non-member' if non_member else request.form.get('member_number', '').strip()
            if not name or not member:
                specs = _get_specs(item)
                return render_template(
                    'checkout_scan.html', item=item, specs=specs,
                    is_checked_out=bool(existing), error="Please fill in all fields."
                )
            notes = request.form.get('checkout_notes', '').strip()
            phone = request.form.get('phone', '').strip()
            cur = db.execute(
                "INSERT INTO checkouts (equipment_id, customer_name, member_number, phone, checkout_notes) VALUES (?, ?, ?, ?, ?)",
                (equipment_id, name, member, phone or None, notes or None)
            )
            checkout_id = cur.lastrowid
            photo_file = request.files.get('condition_photo')
            if item['category'] == 'paddle' and photo_file and photo_file.filename:
                fname = _save_checkout_photo(photo_file, checkout_id)
                db.execute("UPDATE checkouts SET photo_filename=? WHERE id=?", (fname, checkout_id))
            db.commit()
            return redirect(url_for('checkout_confirm', equipment_id=equipment_id))

        if item['under_maintenance']:
            return render_template('checkout_unavailable.html', item=item, joined=False, maintenance=True)

        if existing:
            return redirect(url_for('checkout_unavailable', equipment_id=equipment_id))

        specs = _get_specs(item)
        return render_template('checkout_scan.html', item=item, specs=specs, is_checked_out=False)

    @app.route('/checkout/<int:equipment_id>/confirm')
    def checkout_confirm(equipment_id):
        db = get_db()
        item = db.execute("SELECT name FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        checkout = db.execute(
            "SELECT customer_name, member_number, phone, checked_out_at FROM checkouts WHERE equipment_id = ? ORDER BY id DESC LIMIT 1",
            (equipment_id,)
        ).fetchone()
        return render_template('checkout_confirm.html', item=item, checkout=checkout)

    @app.route('/checkout/<int:equipment_id>/unavailable', methods=['GET', 'POST'])
    def checkout_unavailable(equipment_id):
        db = get_db()
        item = db.execute("SELECT name FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        if request.method == 'POST':
            name   = request.form.get('customer_name', '').strip()
            member = request.form.get('member_number', '').strip()
            phone  = request.form.get('phone', '').strip()
            if name and member:
                db.execute(
                    "INSERT INTO waitlist (equipment_id, customer_name, member_number, phone) VALUES (?, ?, ?, ?)",
                    (equipment_id, name, member, phone or None)
                )
                db.commit()
            return render_template('checkout_unavailable.html', item=item, joined=True)
        return render_template('checkout_unavailable.html', item=item, joined=False)

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app


def _save_checkout_photo(file, checkout_id):
    img = PILImage.open(file.stream).convert('RGB')
    if max(img.size) > 1200:
        img.thumbnail((1200, 1200), PILImage.LANCZOS)
    photos_dir = Path(app.root_path) / 'static' / 'checkout_photos'
    photos_dir.mkdir(parents=True, exist_ok=True)
    filename = f"checkout_{checkout_id}.jpg"
    img.save(photos_dir / filename, 'JPEG', quality=80)
    return filename


def _get_specs(item):
    specs = []
    for i in range(1, 6):
        label = item[f'spec{i}_label']
        value = item[f'spec{i}_value']
        if label and value:
            specs.append((label, value))
    return specs


app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
