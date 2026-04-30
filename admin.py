import io
import csv
import zipfile
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, current_app, send_from_directory, send_file, jsonify
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


def _member_name_patterns(q):
    """Build LIKE patterns for member name search against "Last, First" stored format.

    Single token  ("Trey")   → last-name prefix OR first-name prefix
    Two+ tokens   ("Trey F") → "First LastPrefix" → pattern "F%, Trey%"
    Returns (name_patterns_list, number_pattern_or_None).
    """
    clean = q.replace(',', '').strip()
    tokens = clean.split()
    if not tokens:
        return [], None
    if len(tokens) == 1:
        t = tokens[0]
        return [f'{t}%', f'%, {t}%'], f'{t}%'
    first = tokens[0]
    last_prefix = ' '.join(tokens[1:])
    return [f'{last_prefix}%, {first}%'], None

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
        SELECT c.id, c.customer_name, c.member_number, c.phone, c.checked_out_at,
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

    waitlist_members = {}
    for w in db.execute(
        "SELECT equipment_id, customer_name, member_number FROM waitlist ORDER BY created_at"
    ).fetchall():
        waitlist_members.setdefault(w['equipment_id'], []).append(
            {'name': w['customer_name'], 'member': w['member_number']}
        )

    active = []
    for row in rows:
        due_label, is_overdue = _due_back(row['checked_out_at'])
        active.append({
            'id':             row['id'],
            'customer_name':  row['customer_name'],
            'member_number':  row['member_number'],
            'checked_out_at': row['checked_out_at'],
            'phone':          row['phone'],
            'checkout_notes': row['checkout_notes'],
            'photo_filename': row['photo_filename'],
            'equipment_id':   row['equipment_id'],
            'equipment_name': row['equipment_name'],
            'category':       row['category'],
            'due_label':      due_label,
            'is_overdue':     is_overdue,
            'waitlist_count': waitlist_counts.get(row['equipment_id'], 0),
        })

    from flask import session
    return render_template('admin/dashboard.html', active=active, q=q,
                           waitlist_members=waitlist_members,
                           staff_names=current_app.config.get('STAFF_NAMES', []),
                           current_staff=session.get('staff_name', ''))


@admin_bp.route('/checkout/<int:checkout_id>/photo', methods=['POST'])
@login_required
def checkout_photo_upload(checkout_id):
    from PIL import Image as PILImage
    photo_file = request.files.get('photo')
    if photo_file and photo_file.filename:
        db = get_db()
        row = db.execute("SELECT photo_filename, equipment_id FROM checkouts WHERE id=?", (checkout_id,)).fetchone()
        if row and row['photo_filename']:
            old = Path(current_app.root_path) / 'static' / 'checkout_photos' / row['photo_filename']
            if old.exists():
                old.unlink()
        img = PILImage.open(photo_file.stream).convert('RGB')
        if max(img.size) > 1200:
            img.thumbnail((1200, 1200), PILImage.LANCZOS)
        photos_dir = Path(current_app.root_path) / 'static' / 'checkout_photos'
        photos_dir.mkdir(parents=True, exist_ok=True)
        fname = f"checkout_{checkout_id}.jpg"
        img.save(photos_dir / fname, 'JPEG', quality=80)
        db.execute("UPDATE checkouts SET photo_filename=? WHERE id=?", (fname, checkout_id))
        _log('Upload Photo', f"Checkout #{checkout_id}")
        db.commit()
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/return/<int:checkout_id>', methods=['POST'])
@login_required
def mark_returned(checkout_id):
    notes = request.form.get('notes', '')
    staff = request.form.get('staff_name', '').strip()
    db = get_db()
    row = db.execute("SELECT photo_filename, equipment_id FROM checkouts WHERE id=?", (checkout_id,)).fetchone()
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
        detail = (f"{checkout['equipment_name']} — {checkout['customer_name']} (#{checkout['member_number']})"
                  + (f" — Notes: {notes}" if notes else ""))
        db.execute(
            "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
            (staff or 'Unknown', 'Mark Returned', detail)
        )
        # Notify waitlist members
        if row:
            waitlist = db.execute(
                "SELECT customer_name, phone FROM waitlist WHERE equipment_id=? ORDER BY created_at",
                (row['equipment_id'],)
            ).fetchall()
            if waitlist:
                from sms import send_sms
                for w in waitlist:
                    if w['phone']:
                        send_sms(w['phone'],
                                 f"Hi {w['customer_name'].split()[0]}, the {checkout['equipment_name']} demo is now "
                                 f"available at the SACC Tennis Shop. Stop by the front desk to check it out. Reply STOP to opt out.")
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
        ORDER BY CASE e.category WHEN 'racquet' THEN 0 ELSE 1 END, e.name
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
    from flask import session
    return render_template('admin/equipment_list.html', equipment=rows,
                           staff_names=current_app.config.get('STAFF_NAMES', []),
                           current_staff=session.get('staff_name', ''))


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


@admin_bp.route('/members/search')
@login_required
def member_search():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    name_patterns, number_pattern = _member_name_patterns(q)
    if not name_patterns:
        return jsonify([])
    db = get_db()
    or_clauses = ['m.member_name LIKE ?' for _ in name_patterns]
    params = list(name_patterns)
    if number_pattern:
        or_clauses.append('m.member_number LIKE ?')
        params.append(number_pattern)
    where = ' OR '.join(or_clauses)
    rows = db.execute(
        f'SELECT m.member_name, m.member_number, mc.phone1 FROM members m LEFT JOIN members_contact mc ON m.member_number = mc.member_number WHERE {where} ORDER BY m.member_name LIMIT 50',
        params
    ).fetchall()
    return jsonify([{'name': r['member_name'], 'number': r['member_number'], 'phone1': r['phone1'] or ''} for r in rows])


@admin_bp.route('/members')
@login_required
def member_search_page():
    db = get_db()
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        name_patterns, number_pattern = _member_name_patterns(q)
        if name_patterns:
            or_clauses = ['member_name LIKE ?' for _ in name_patterns]
            params = list(name_patterns)
            if number_pattern:
                or_clauses.append('member_number LIKE ?')
                params.append(number_pattern)
            where = ' OR '.join(or_clauses)
            rows = db.execute(
                f'SELECT id, member_name, member_number, email1, email2, phone1, phone2 FROM members_contact WHERE {where} ORDER BY member_name',
                params
            ).fetchall()
    return render_template('admin/member_search.html', rows=rows, q=q)


@admin_bp.route('/members/<int:member_id>/update', methods=['POST'])
@login_required
def member_contact_update(member_id):
    field = request.form.get('field', '')
    value = request.form.get('value', '').strip() or None
    allowed = {'email1', 'email2', 'phone1', 'phone2'}
    if field in allowed:
        db = get_db()
        db.execute(f"UPDATE members_contact SET {field} = ? WHERE id = ?", (value, member_id))
        db.commit()
    q = request.form.get('q', '')
    return redirect(url_for('admin.member_search_page', q=q))


@admin_bp.route('/members/<int:member_id>/edit', methods=['POST'])
@login_required
def member_edit(member_id):
    from database import format_phone
    db = get_db()
    contact = db.execute("SELECT member_number FROM members_contact WHERE id=?", (member_id,)).fetchone()
    if not contact:
        return redirect(url_for('admin.member_search_page'))
    old_number = contact['member_number']
    last   = request.form.get('last_name', '').strip()
    first  = request.form.get('first_name', '').strip()
    name   = f'{last}, {first}' if last and first else (last or first)
    number = request.form.get('member_number', '').strip()
    email1 = request.form.get('email1', '').strip() or None
    email2 = request.form.get('email2', '').strip() or None
    phone1 = format_phone(request.form.get('phone1', '').strip()) or None
    phone2 = format_phone(request.form.get('phone2', '').strip()) or None
    q      = request.form.get('q', '')
    if name and number:
        db.execute(
            "UPDATE members_contact SET member_name=?, member_number=?, email1=?, email2=?, phone1=?, phone2=? WHERE id=?",
            (name, number, email1, email2, phone1, phone2, member_id)
        )
        db.execute(
            "UPDATE members SET member_name=?, member_number=? WHERE member_number=?",
            (name, number, old_number)
        )
        db.commit()
    return redirect(url_for('admin.member_search_page', q=q))


@admin_bp.route('/members/add', methods=['POST'])
@login_required
def member_add():
    import re
    db = get_db()
    last   = request.form.get('last_name', '').strip()
    first  = request.form.get('first_name', '').strip()
    name   = f'{last}, {first}' if last and first else (last or first)
    number = request.form.get('member_number', '').strip()
    email1 = request.form.get('email1', '').strip() or None
    email2 = request.form.get('email2', '').strip() or None
    phone1 = request.form.get('phone1', '').strip() or None
    phone2 = request.form.get('phone2', '').strip() or None
    q      = request.form.get('q', '')

    # Strip leading zeros from member number
    match = re.match(r'^0*(\d+)([A-Za-z]?)$', number)
    if match:
        number = match.group(1) + match.group(2).upper()

    if name and number:
        try:
            db.execute("INSERT INTO members (member_name, member_number) VALUES (?, ?)", (name, number))
            db.execute(
                "INSERT INTO members_contact (member_name, member_number, email1, email2, phone1, phone2) VALUES (?, ?, ?, ?, ?, ?)",
                (name, number, email1, email2, phone1, phone2)
            )
            db.commit()
        except Exception:
            pass  # Duplicate number — silently skip

    return redirect(url_for('admin.member_search_page', q=q))


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
            """
        ).fetchall()
    return render_template('admin/history.html', rows=rows, q=q)


@admin_bp.route('/checkout/<int:checkout_id>/unmark-returned', methods=['POST'])
@login_required
def unmark_returned(checkout_id):
    db = get_db()
    row = db.execute("SELECT equipment_id FROM checkouts WHERE id = ?", (checkout_id,)).fetchone()
    if row:
        conflict = db.execute(
            "SELECT id FROM checkouts WHERE equipment_id = ? AND returned_at IS NULL AND id != ?",
            (row['equipment_id'], checkout_id)
        ).fetchone()
        if not conflict:
            db.execute("UPDATE checkouts SET returned_at = NULL, return_notes = NULL WHERE id = ?", (checkout_id,))
            db.commit()
    return redirect(url_for('admin.history'))


@admin_bp.route('/equipment/<int:equipment_id>/delete', methods=['POST'])
@login_required
def equipment_delete(equipment_id):
    from flask import session
    db = get_db()
    item = db.execute("SELECT name FROM equipment WHERE id=?", (equipment_id,)).fetchone()
    if item is None:
        return redirect(url_for('admin.equipment_list'))
    if request.form.get('pin') != current_app.config['RETIRE_PIN']:
        rows = db.execute(
            """SELECT e.*, CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END AS is_checked_out
               FROM equipment e
               LEFT JOIN checkouts c ON e.id = c.equipment_id AND c.returned_at IS NULL
               ORDER BY e.active DESC, e.category, e.name"""
        ).fetchall()
        return render_template('admin/equipment_list.html', equipment=rows,
                               staff_names=current_app.config.get('STAFF_NAMES', []),
                               current_staff=session.get('staff_name', ''),
                               delete_equip_error=True,
                               delete_equip_error_id=equipment_id,
                               delete_equip_error_name=item['name'])
    db.execute("DELETE FROM checkouts WHERE equipment_id=?", (equipment_id,))
    db.execute("DELETE FROM waitlist WHERE equipment_id=?", (equipment_id,))
    db.execute("DELETE FROM equipment WHERE id=?", (equipment_id,))
    db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
               (session.get('staff_name', 'Unknown'), 'Delete Equipment', item['name']))
    db.commit()
    return redirect(url_for('admin.equipment_list'))


@admin_bp.route('/equipment/<int:equipment_id>/service', methods=['POST'])
@login_required
def equipment_service(equipment_id):
    staff = request.form.get('staff_name', '').strip()
    db = get_db()
    item = db.execute("SELECT name, under_maintenance FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    db.execute("UPDATE equipment SET under_maintenance = 1 - under_maintenance WHERE id = ?", (equipment_id,))
    if item:
        action = 'Cleared Maintenance' if item['under_maintenance'] else 'Marked Under Maintenance'
        db.execute(
            "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
            (staff or 'Unknown', action, item['name'])
        )
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


@admin_bp.route('/label/<int:equipment_id>/download')
@login_required
def label_download(equipment_id):
    db = get_db()
    item = db.execute("SELECT name FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
    if item is None:
        return redirect(url_for('admin.equipment_list'))
    label_filename = generate_label(equipment_id, item['name'], current_app.config['QR_BASE_URL'])
    label_path = LABEL_DIR / label_filename
    safe_name = item['name'].replace('/', '-').replace('\\', '-')
    return send_file(label_path, as_attachment=True, download_name=f"{safe_name}-label.png")


@admin_bp.route('/qr-code-list')
@login_required
def qr_code_list():
    import base64
    from pathlib import Path
    db = get_db()
    rows = db.execute(
        "SELECT id, name, category, qr_filename, notes FROM equipment WHERE active = 1 ORDER BY category, name"
    ).fetchall()
    qr_dir = Path(current_app.root_path) / 'static' / 'qrcodes'
    items = []
    for r in rows:
        b64 = None
        if r['qr_filename']:
            path = qr_dir / r['qr_filename']
            if path.exists():
                b64 = base64.b64encode(path.read_bytes()).decode()
        items.append({'name': r['name'], 'category': r['category'], 'qr_b64': b64, 'notes': r['notes']})
    racquets = [i for i in items if i['category'] == 'racquet']
    paddles  = [i for i in items if i['category'] == 'paddle']
    from datetime import datetime
    now = datetime.now().strftime('%B %-d, %Y')
    return render_template('admin/qr_code_list.html', racquets=racquets, paddles=paddles, now=now)


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
               c.customer_name, c.member_number, c.phone, c.checkout_notes,
               c.checked_out_at, c.returned_at, c.return_notes
        FROM checkouts c
        JOIN equipment e ON c.equipment_id = e.id
        ORDER BY c.checked_out_at DESC
        """
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['ID', 'Equipment', 'Category', 'Member Name', 'Member #', 'Phone',
                'Checkout Notes', 'Checked Out (CST)', 'Returned (CST)', 'Return Notes'])
    for r in rows:
        w.writerow([r['id'], r['equipment'], r['category'], r['customer_name'],
                    r['member_number'], r['phone'] or '', r['checkout_notes'] or '',
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
