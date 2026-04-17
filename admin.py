from flask import Blueprint, render_template, request, redirect, url_for, current_app, send_from_directory, send_file
from pathlib import Path
from database import get_db
from auth import login_required
from qr_utils import generate_qr

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
@login_required
def dashboard():
    db = get_db()
    active = db.execute(
        """
        SELECT c.id, c.customer_name, c.member_number, c.checked_out_at,
               e.name AS equipment_name, e.category
        FROM checkouts c
        JOIN equipment e ON c.equipment_id = e.id
        WHERE c.returned_at IS NULL
        ORDER BY c.checked_out_at DESC
        """
    ).fetchall()
    return render_template('admin/dashboard.html', active=active)


@admin_bp.route('/return/<int:checkout_id>', methods=['POST'])
@login_required
def mark_returned(checkout_id):
    notes = request.form.get('notes', '')
    db = get_db()
    db.execute(
        "UPDATE checkouts SET returned_at = datetime('now'), return_notes = ? WHERE id = ?",
        (notes, checkout_id)
    )
    db.commit()
    return redirect(url_for('admin.dashboard'))


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
        ORDER BY e.category, e.name
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
               spec3_label, spec3_value, spec4_label, spec4_value, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
              notes=?
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
