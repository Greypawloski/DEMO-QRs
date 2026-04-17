from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
from zoneinfo import ZoneInfo
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
            SELECT e.*,
                   CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END AS is_checked_out
            FROM equipment e
            LEFT JOIN checkouts c ON e.id = c.equipment_id AND c.returned_at IS NULL
            WHERE e.active = 1
            ORDER BY e.category, e.name
            """
        ).fetchall()
        return render_template('home.html', equipment=rows)

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
            member = request.form.get('member_number', '').strip()
            if not name or not member:
                specs = _get_specs(item)
                return render_template(
                    'checkout_scan.html', item=item, specs=specs,
                    is_checked_out=bool(existing), error="Please fill in all fields."
                )
            db.execute(
                "INSERT INTO checkouts (equipment_id, customer_name, member_number) VALUES (?, ?, ?)",
                (equipment_id, name, member)
            )
            db.commit()
            return redirect(url_for('checkout_confirm', equipment_id=equipment_id))

        if existing:
            return redirect(url_for('checkout_unavailable', equipment_id=equipment_id))

        specs = _get_specs(item)
        return render_template('checkout_scan.html', item=item, specs=specs, is_checked_out=False)

    @app.route('/checkout/<int:equipment_id>/confirm')
    def checkout_confirm(equipment_id):
        db = get_db()
        item = db.execute("SELECT name FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        return render_template('checkout_confirm.html', item=item)

    @app.route('/checkout/<int:equipment_id>/unavailable')
    def checkout_unavailable(equipment_id):
        db = get_db()
        item = db.execute("SELECT name FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        return render_template('checkout_unavailable.html', item=item)

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app


def _get_specs(item):
    specs = []
    for i in range(1, 5):
        label = item[f'spec{i}_label']
        value = item[f'spec{i}_value']
        if label and value:
            specs.append((label, value))
    return specs


app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
