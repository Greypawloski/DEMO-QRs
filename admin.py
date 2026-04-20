import io
import csv
import zipfile
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, current_app, send_from_directory, send_file
from pathlib import Path
from database import get_db
from auth import login_required
from qr_utils import generate_qr, generate_label, LABEL_DIR


def _due_back(checked_out_at_str):
    """Return (label, is_overdue) for a checkout timestamp (UTC)."""
    checked_out = datetime.fromisoformat(checked_out_at_str).replace(tzinfo=timezone.utc)
    due = checked_out + timedelta(hours=72)
    delta = due - datetime.now(timezone.utc)
    total_secs = delta.total_seconds()
    overdue = total_secs < 0
    secs = abs(total_secs)
    hours = int(secs // 3600)
    mins  = int((secs % 3600) // 60)
    if hours >= 48:
        label = f"{hours // 24}d {hours % 24}h {'overdue' if overdue else 'left'}"
    else:
        label = f"{hours}h {mins}m {'overdue' if overdue else 'left'}"
    return label, overdue

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _log(action, details=None):
    from flask import session
    staff = session.get('staff_name', 'Unknown')
    get_db().execute(
        "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
        (staff, action, details)
    )


@admin_bp.route('/')
@login_required
def dashboard():
    db  = get_db()
    q   = request.args.get('q', '').strip()
    sql = """
        SELECT c.id, c.customer_name, c.member_number, c.checked_out_at,
               c.checkout_notes, c.photo_filename,
               e.id AS equipment_id, e.name AS equipment_name, e.category
        FROM checkouts c
        JOIN equipment e ON c.equipment_id = e.id
        WHERE c.returned_at IS NULL
    """
    params = []
    if q:
        sql += " AND (c.customer_name LIKE ? OR c.member_number LIKE ?)"
        params = [f'%{q}%', f'%{q}%']
    sql += " ORDER BY c.checked_out_at DESC"
    rows = db.execute(sql, params).fetchall()

    waitlist_counts = {
        w['equipment_id']: w['cnt']
        for w in db.execute(
            "SELECT equipment_id, COUNT(*) AS cnt FROM waitlist GROUP BY equipment_id"
        ).fetchall()
    }

    active = []
    for row in rows:
        due_label, is_overdue = _due_back(row['checked_out_at'])
        active.append({
            'id':             row['id'],
            'customer_name':  row['customer_name'],
            'member_number':  row['member_number'],
            'checked_out_at': row['checked_out_at'],
            'checkout_notes': row['checkout_notes'],
            'photo_filename': row['photo_filename'],
            'equipment_id':   row['equipment_id'],
            'equipment_name': row['equipment_name'],
            'category':       row['category'],
            'due_label':      due_label,
            'is_overdue':     is_overdue,
            'waitlist_count': waitlist_counts.get(row['equipment_id'], 0),
        })

    return render_template('admin/dashboard.html', active=active, q=q)


@admin_bp.route('/return/<int:checkout_id>', methods=['POST'])
@login_required
def mark_returned(checkout_id):
    notes = request.form.get('notes', '')
    db = get_db()
    row = db.execute("SELECT photo_filename FROM checkouts WHERE id=?", (checkout_id,)).fetchone()
    if row and row['photo_filename']:
        photo_path = Path(current_app.root_path) / 'static' / 'checkout_photos' / row['photo_filename']
        if photo_path.exists():
            photo_path.unlink()
    checkout = db.execute(
        "SELECT c.return_notes, e.name AS equipment_name, c.customer_name, c.member_number "
        "FROM checkouts c JOIN equipment e ON c.equipment_id = e.id WHERE c.id = ?",
        (checkout_id,)
    ).fetchone()
    db.execute(
        "UPDATE checkouts SET returned_at = datetime('now'), return_notes = ? WHERE id = ?",
        (notes, checkout_id)
    )
    if checkout:
        _log('Mark Returned',
             f"{checkout['equipment_name']} — {checkout['customer_name']} (#{checkout['member_number']})"
             + (f" — Notes: {notes}" if notes else ""))
    db.commit()
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/kiosk')
@login_required
def kiosk_view():
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


@admin_bp.route('/equipment')
@login_required
def equipment_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT e.*,
               CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END AS is_checked_out
        FROM equipment e
        LEFT JOIN checkouts c ON e.id = c.equipment_id AND c.returned_at IS NULL
        ORDER BY e.active DESC, e.category, e.name
        """
    ).fetchall()
    return render_template('admin/equipment_list.html', equipment=rows)


@admin_bp.route('/equipment/new', methods=['GET', 'POST'])
@login_required
def equipment_new():
    if request.method == 'POST':
        db = get_db()
        cur = db.execute(
            """
            INSERT INTO equipment
              (name, category,
               spec1_label, spec1_value, spec2_label, spec2_value,
               spec3_label, spec3_value, spec4_label, spec4_value,
               spec5_label, spec5_value, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.form['name'].strip(),
                request.form['category'],
                request.form.get('spec1_label', '').strip(),
                request.form.get('spec1_value', '').strip(),
                request.form.get('spec2_label', '').strip(),
                request.form.get('spec2_value', '').strip(),
                request.form.get('spec3_label', '').strip(),
                request.form.get('spec3_value', '').strip(),
                request.form.get('spec4_label', '').strip(),
                request.form.get('spec4_value', '').strip(),
                request.form.get('spec5_label', '').strip(),
                request.form.get('spec5_value', '').strip(),
                request.form.get('notes', '').strip(),
            )
        )
        equipment_id = cur.lastrowid
        filename = generate_qr(equipment_id, current_app.config['QR_BASE_URL'])
        db.execute("UPDATE equipment SET qr_filename = ? WHERE id = ?", (filename, equipment_id))
        db.commit()
        return redirect(url_for('admin.equipment_list'))
    return render_template('admin/equipment_form.html', item=None)


@admin_bp.route('/equipment/<int:equipment_id>/edit', methods=['GET', 'POST'])
@login_required
def equipment_edit(equipment_id):
    db = get_db()
    item = db.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if item is None:
        return redirect(url_for('admin.equipment_list'))

    if request.method == 'POST':
        db.execute(
            """
            UPDATE equipment SET
              name=?, category=?,
              spec1_label=?, spec1_value=?, spec2_label=?, spec2_value=?,
              spec3_label=?, spec3_value=?, spec4_label=?, spec4_value=?,
              spec5_label=?, spec5_value=?, notes=?
            WHERE id=?
            """,
            (
                request.form['name'].strip(),
                request.form['category'],
                request.form.get('spec1_label', '').strip(),
                request.form.get('spec1_value', '').strip(),
                request.form.get('spec2_label', '').strip(),
                request.form.get('spec2_value', '').strip(),
                request.form.get('spec3_label', '').strip(),
                request.form.get('spec3_value', '').strip(),
                request.form.get('spec4_label', '').strip(),
                request.form.get('spec4_value', '').strip(),
                request.form.get('spec5_label', '').strip(),
                request.form.get('spec5_value', '').strip(),
                request.form.get('notes', '').strip(),
                equipment_id,
            )
        )
        filename = generate_qr(equipment_id, current_app.config['QR_BASE_URL'])
        db.execute("UPDATE equipment SET qr_filename = ? WHERE id = ?", (filename, equipment_id))
        db.commit()
        return redirect(url_for('admin.equipment_list'))
    return render_template('admin/equipment_form.html', item=item)


@admin_bp.route('/equipment/<int:equipment_id>/toggle', methods=['POST'])
@login_required
def equipment_toggle(equipment_id):
    db = get_db()
    item = db.execute("SELECT active FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if item:
        # Both Retire and Activate require PIN
        if request.form.get('retire_pin') != current_app.config['RETIRE_PIN']:
            rows = db.execute(
                """
                SELECT e.*,
                       CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END AS is_checked_out
                FROM equipment e
                LEFT JOIN checkouts c ON e.id = c.equipment_id AND c.returned_at IS NULL
                ORDER BY e.category, e.name
                """
            ).fetchall()
            pin_error_name = request.form.get('equipment_name', '')
            return render_template('admin/equipment_list.html', equipment=rows,
                                   pin_error=equipment_id, pin_error_name=pin_error_name)
    db.execute("UPDATE equipment SET active = 1 - active WHERE id = ?", (equipment_id,))
    db.commit()
    return redirect(url_for('admin.equipment_list'))


@admin_bp.route('/qr/<int:equipment_id>')
@login_required
def qr_image(equipment_id):
    db = get_db()
    item = db.execute("SELECT qr_filename FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if item is None or not item['qr_filename']:
        return "QR code not found", 404
    return send_from_directory('static/qrcodes', item['qr_filename'])


@admin_bp.route('/qr/<int:equipment_id>/download')
@login_required
def qr_download(equipment_id):
    db = get_db()
    item = db.execute("SELECT name, qr_filename FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if item is None or not item['qr_filename']:
        return "QR code not found", 404
    path = Path(current_app.root_path) / 'static' / 'qrcodes' / item['qr_filename']
    safe_name = item['name'].replace('/', '-')
    return send_file(path, as_attachment=True, download_name=f"{safe_name}-QR.png")


@admin_bp.route('/qr/<int:equipment_id>/print')
@login_required
def qr_print(equipment_id):
    db = get_db()
    item = db.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if item is None:
        return redirect(url_for('admin.equipment_list'))
    return render_template('admin/qr_print.html', item=item)


@admin_bp.route('/history')
@login_required
def history():
    db = get_db()
    q = request.args.get('q', '').strip()
    if q:
        pattern = f'%{q}%'
        rows = db.execute(
            """
            SELECT c.*, e.name AS equipment_name, e.category
            FROM checkouts c
            JOIN equipment e ON c.equipment_id = e.id
            WHERE c.customer_name LIKE ? OR c.member_number LIKE ?
            ORDER BY c.checked_out_at DESC
            LIMIT 200
            """,
            (pattern, pattern)
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT c.*, e.name AS equipment_name, e.category
            FROM checkouts c
            JOIN equipment e ON c.equipment_id = e.id
            ORDER BY c.checked_out_at DESC
            LIMIT 200
            """
        ).fetchall()
    return render_template('admin/history.html', rows=rows, q=q)


@admin_bp.route('/equipment/<int:equipment_id>/service', methods=['POST'])
@login_required
def equipment_service(equipment_id):
    db = get_db()
    item = db.execute("SELECT name, under_maintenance FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    db.execute("UPDATE equipment SET under_maintenance = 1 - under_maintenance WHERE id = ?", (equipment_id,))
    if item:
        action = 'Cleared Maintenance' if item['under_maintenance'] else 'Marked Under Maintenance'
        _log(action, item['name'])
    db.commit()
    return redirect(url_for('admin.equipment_list'))


@admin_bp.route('/activity')
@login_required
def activity_log():
    rows = get_db().execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    return render_template('admin/activity_log.html', rows=rows)


@admin_bp.route('/reports')
@login_required
def reports():
    db = get_db()

    popular = db.execute(
        """
        SELECT e.name, e.category, COUNT(c.id) AS total
        FROM equipment e
        LEFT JOIN checkouts c ON e.id = c.equipment_id
        GROUP BY e.id ORDER BY total DESC LIMIT 20
        """
    ).fetchall()

    durations = db.execute(
        """
        SELECT e.name, e.category, COUNT(c.id) AS total,
               ROUND(AVG((julianday(c.returned_at) - julianday(c.checked_out_at)) * 24), 1) AS avg_hours
        FROM equipment e
        JOIN checkouts c ON e.id = c.equipment_id
        WHERE c.returned_at IS NOT NULL
        GROUP BY e.id ORDER BY total DESC
        """
    ).fetchall()

    members = db.execute(
        """
        SELECT customer_name, member_number, COUNT(*) AS total,
               MAX(checked_out_at) AS last_checkout
        FROM checkouts
        GROUP BY member_number
        ORDER BY total DESC LIMIT 30
        """
    ).fetchall()

    return render_template('admin/reports.html', popular=popular, durations=durations, members=members)


@admin_bp.route('/labels/download-zip')
@login_required
def labels_download_zip():
    db = get_db()
    items = db.execute(
        "SELECT id, name FROM equipment WHERE active = 1 ORDER BY name"
    ).fetchall()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            label_filename = generate_label(item['id'], item['name'], current_app.config['QR_BASE_URL'])
            label_path = LABEL_DIR / label_filename
            safe_name = item['name'].replace('/', '-').replace('\\', '-')
            zf.write(label_path, f"{safe_name}.png")

    zip_buf.seek(0)
    return send_file(zip_buf, as_attachment=True,
                     download_name='SACC-labels.zip',
                     mimetype='application/zip')


def _fmt_central(dt_str):
    if not dt_str:
        return ''
    from zoneinfo import ZoneInfo
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo('America/Chicago')).strftime('%-m/%-d/%Y %-I:%M %p')


@admin_bp.route('/history/export-csv')
@login_required
def history_export_csv():
    db = get_db()
    rows = db.execute(
        """
        SELECT c.id, e.name AS equipment, e.category,
               c.customer_name, c.member_number, c.checkout_notes,
               c.checked_out_at, c.returned_at, c.return_notes
        FROM checkouts c
        JOIN equipment e ON c.equipment_id = e.id
        ORDER BY c.checked_out_at DESC
        """
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['ID', 'Equipment', 'Category', 'Member Name', 'Member #',
                'Checkout Notes', 'Checked Out (CST)', 'Returned (CST)', 'Return Notes'])
    for r in rows:
        w.writerow([r['id'], r['equipment'], r['category'], r['customer_name'],
                    r['member_number'], r['checkout_notes'] or '',
                    _fmt_central(r['checked_out_at']), _fmt_central(r['returned_at']),
                    r['return_notes'] or ''])
    buf.seek(0)
    return send_file(io.BytesIO(buf.getvalue().encode()),
                     as_attachment=True, download_name='checkout-history.csv',
                     mimetype='text/csv')


@admin_bp.route('/waitlist/<int:equipment_id>/clear', methods=['POST'])
@login_required
def waitlist_clear(equipment_id):
    db = get_db()
    db.execute("DELETE FROM waitlist WHERE equipment_id = ?", (equipment_id,))
    db.commit()
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/regenerate-all-qr', methods=['POST'])
@login_required
def regenerate_all_qr():
    if request.form.get('regen_pin') != current_app.config['RETIRE_PIN']:
        rows = get_db().execute(
            """
            SELECT e.*, CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END AS is_checked_out
            FROM equipment e
            LEFT JOIN checkouts c ON e.id = c.equipment_id AND c.returned_at IS NULL
            ORDER BY e.category, e.name
            """
        ).fetchall()
        return render_template('admin/equipment_list.html', equipment=rows, regen_pin_error=True)
    db = get_db()
    items = db.execute("SELECT id FROM equipment WHERE active = 1").fetchall()
    for item in items:
        filename = generate_qr(item['id'], current_app.config['QR_BASE_URL'])
        db.execute("UPDATE equipment SET qr_filename = ? WHERE id = ?", (filename, item['id']))
    db.commit()
    return redirect(url_for('admin.equipment_list'))
