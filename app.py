from flask import Flask, render_template, request, redirect, url_for, g, session
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from PIL import Image as PILImage
import config
from database import get_db, init_db, init_app as db_init_app, sync_member_phone, format_phone
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

    @app.context_processor
    def inject_nav_counts():
        from flask import session
        if not session.get('admin_logged_in'):
            return {}
        try:
            db = get_db()
            overdue_restrings = db.execute(
                "SELECT COUNT(*) FROM restrings WHERE status='complete' AND completed_at < datetime('now', '-7 days')"
            ).fetchone()[0]
            ready_restrings = db.execute(
                "SELECT COUNT(*) FROM restrings WHERE status='complete'"
            ).fetchone()[0]
            pending_restrings = db.execute(
                "SELECT COUNT(*) FROM restrings WHERE status='pending'"
            ).fetchone()[0]
            active_demos = db.execute(
                "SELECT COUNT(*) FROM checkouts WHERE returned_at IS NULL"
            ).fetchone()[0]
            approaching_charge = db.execute(
                """SELECT COUNT(DISTINCT customer_name || member_number)
                   FROM checkouts
                   WHERE returned_at IS NULL
                   AND CAST((julianday('now') - julianday(checked_out_at)) AS INTEGER) >= 25"""
            ).fetchone()[0]
        except Exception:
            return {}
        return {
            'nav_overdue_restrings':  overdue_restrings,
            'nav_ready_restrings':    ready_restrings,
            'nav_pending_restrings':  pending_restrings,
            'nav_active_demos':       active_demos,
            'nav_approaching_charge': approaching_charge,
        }

    # Auto-initialize DB on first request if it doesn't exist; run safe migrations
    @app.before_request
    def ensure_db():
        import os
        if not os.path.exists(app.config['DB_PATH']):
            with app.app_context():
                init_db()
        else:
            db = get_db()
            db.executescript("""
                CREATE TABLE IF NOT EXISTS non_members (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT NOT NULL,
                    phone      TEXT,
                    notes      TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_non_members_name_lower ON non_members(LOWER(name));
            """)

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

    @app.route('/admin/checkout/<int:equipment_id>', methods=['GET', 'POST'])
    def admin_checkout(equipment_id):
        from auth import login_required as lr
        db = get_db()
        item = db.execute(
            "SELECT * FROM equipment WHERE id = ? AND active = 1", (equipment_id,)
        ).fetchone()
        if item is None:
            return render_template('errors/404.html'), 404

        existing = db.execute(
            "SELECT id FROM checkouts WHERE equipment_id = ? AND returned_at IS NULL",
            (equipment_id,)
        ).fetchone()

        if request.method == 'POST':
            if existing:
                return redirect(url_for('checkout_unavailable', equipment_id=equipment_id))
            name = request.form.get('customer_name', '').strip()
            non_member = request.form.get('non_member') == '1'
            if non_member:
                member = 'Non-member'
            else:
                member = request.form.get('member_number', '').strip()
                suffix = request.form.get('member_suffix', '').strip()
                if suffix:
                    member = member + suffix
            if not name or not member:
                specs = _get_specs(item)
                return render_template(
                    'admin_checkout.html', item=item, specs=specs,
                    error="Please fill in all required fields."
                )
            notes = request.form.get('checkout_notes', '').strip()
            phone = format_phone(request.form.get('phone', '').strip())
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
            sync_member_phone(db, member, phone)
            return redirect(url_for('checkout_confirm', equipment_id=equipment_id))

        if item['under_maintenance']:
            return render_template('checkout_unavailable.html', item=item, joined=False, maintenance=True)
        if existing:
            return redirect(url_for('checkout_unavailable', equipment_id=equipment_id))

        specs = _get_specs(item)
        return render_template('admin_checkout.html', item=item, specs=specs)

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
            if non_member:
                member = 'Non-member'
            else:
                member = request.form.get('member_number', '').strip()
                suffix = request.form.get('member_suffix', '').strip()
                if suffix:
                    member = member + suffix
            if not name or not member:
                specs = _get_specs(item)
                return render_template(
                    'checkout_scan.html', item=item, specs=specs,
                    is_checked_out=bool(existing), error="Please fill in all fields."
                )
            notes = request.form.get('checkout_notes', '').strip()
            phone = format_phone(request.form.get('phone', '').strip())
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
            sync_member_phone(db, member, phone)
            return redirect(url_for('checkout_confirm', equipment_id=equipment_id))

        if item['under_maintenance']:
            return render_template('checkout_unavailable.html', item=item, joined=False, maintenance=True)

        if existing:
            return redirect(url_for('checkout_return_scan', equipment_id=equipment_id))

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

    @app.route('/checkout/<int:equipment_id>/return-scan', methods=['GET', 'POST'])
    def checkout_return_scan(equipment_id):
        from flask import current_app
        db = get_db()
        item = db.execute("SELECT * FROM equipment WHERE id=? AND active=1", (equipment_id,)).fetchone()
        if item is None:
            return render_template('errors/404.html'), 404
        checkout = db.execute(
            "SELECT c.id, c.customer_name, c.member_number, c.photo_filename "
            "FROM checkouts c WHERE c.equipment_id=? AND c.returned_at IS NULL",
            (equipment_id,)
        ).fetchone()
        if not checkout:
            return redirect(url_for('checkout', equipment_id=equipment_id))
        if request.method == 'POST':
            if request.form.get('pin', '') != current_app.config['RETIRE_PIN']:
                return render_template('checkout_return_scan.html', item=item, checkout=checkout,
                                       returned=False, pin_error=True)
            if checkout['photo_filename']:
                photo_path = Path(current_app.root_path) / 'static' / 'checkout_photos' / checkout['photo_filename']
                if photo_path.exists():
                    photo_path.unlink()
            db.execute(
                "UPDATE checkouts SET returned_at=datetime('now') WHERE id=?",
                (checkout['id'],)
            )
            db.execute(
                "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
                ('QR Scan', 'Mark Returned',
                 f"{item['name']} — {checkout['customer_name']} (#{checkout['member_number']}) — returned via QR scan")
            )
            waitlist = db.execute(
                "SELECT customer_name, phone FROM waitlist WHERE equipment_id=? ORDER BY created_at",
                (equipment_id,)
            ).fetchall()
            if waitlist:
                from sms import send_sms
                for w in waitlist:
                    if w['phone']:
                        send_sms(w['phone'],
                                 f"Hi {w['customer_name'].split()[0]}, the {item['name']} demo is now "
                                 f"available at the SACC Tennis Shop. Stop by the front desk to check it out. Reply STOP to opt out.")
            db.commit()
            return render_template('checkout_return_scan.html', item=item, returned=True)
        return render_template('checkout_return_scan.html', item=item, checkout=checkout, returned=False)

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

    @app.route('/checkout/multi', methods=['GET', 'POST'])
    def checkout_multi():
        db = get_db()
        if request.method == 'POST':
            ids_raw = request.form.get('ids', '')
            ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
            name = request.form.get('customer_name', '').strip()
            non_member = request.form.get('non_member') == '1'
            if non_member:
                member = 'Non-member'
            else:
                member = request.form.get('member_number', '').strip()
                suffix = request.form.get('member_suffix', '').strip()
                if suffix:
                    member = member + suffix
            phone = format_phone(request.form.get('phone', '').strip())
            notes = request.form.get('checkout_notes', '').strip()
            if not ids:
                return redirect(url_for('home'))
            if not name or not member:
                items = db.execute(
                    'SELECT id, name, category FROM equipment WHERE id IN ({}) AND active = 1'.format(
                        ','.join('?' * len(ids))), ids
                ).fetchall()
                return render_template('checkout_multi_form.html', items=items, ids_str=ids_raw,
                                       error="Please fill in your name and member number.")
            checked_out = []
            skipped = []
            for equipment_id in ids:
                existing = db.execute(
                    "SELECT id FROM checkouts WHERE equipment_id = ? AND returned_at IS NULL",
                    (equipment_id,)
                ).fetchone()
                if existing:
                    row = db.execute("SELECT name FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
                    skipped.append(row['name'] if row else str(equipment_id))
                    continue
                row = db.execute("SELECT name FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
                db.execute(
                    "INSERT INTO checkouts (equipment_id, customer_name, member_number, phone, checkout_notes) VALUES (?, ?, ?, ?, ?)",
                    (equipment_id, name, member, phone or None, notes or None)
                )
                checked_out.append(row['name'] if row else str(equipment_id))
            db.commit()
            sync_member_phone(db, member, phone)
            session['multi_confirm'] = {
                'customer_name': name,
                'member_number': member,
                'phone': phone,
                'checked_out': checked_out,
                'skipped': skipped,
            }
            return redirect(url_for('checkout_multi_confirm'))

        ids_raw = request.args.get('ids', '')
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
        if not ids:
            return redirect(url_for('home'))
        items = db.execute(
            'SELECT id, name, category FROM equipment WHERE id IN ({}) AND active = 1'.format(
                ','.join('?' * len(ids))), ids
        ).fetchall()
        if not items:
            return redirect(url_for('home'))
        prefill = {
            'name':   request.args.get('prefill_name',   ''),
            'member': request.args.get('prefill_member', ''),
            'phone':  request.args.get('prefill_phone',  ''),
        }
        return render_template('checkout_multi_form.html', items=items, ids_str=ids_raw, prefill=prefill)

    @app.route('/checkout/multi/confirm')
    def checkout_multi_confirm():
        data = session.pop('multi_confirm', None)
        if not data:
            return redirect(url_for('home'))
        return render_template('checkout_multi_confirm.html', data=data)

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
