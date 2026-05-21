import io
import csv
import zipfile
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, current_app, send_from_directory, send_file, jsonify
from pathlib import Path
from database import get_db, format_phone, sync_member_phone, member_flags
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
               c.checkout_notes, c.photo_filename, c.reminder_sent_at, c.second_reminder_sent_at,
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

    now_utc = datetime.now(timezone.utc)
    raw = []
    for row in rows:
        due_label, is_overdue = _due_back(row['checked_out_at'])
        checked_out_dt = datetime.fromisoformat(row['checked_out_at']).replace(tzinfo=timezone.utc)
        days_out = (now_utc - checked_out_dt).total_seconds() / 86400
        raw.append({
            'id':                       row['id'],
            'customer_name':            row['customer_name'],
            'member_number':            row['member_number'],
            'checked_out_at':           row['checked_out_at'],
            'phone':                    row['phone'],
            'checkout_notes':           row['checkout_notes'],
            'photo_filename':           row['photo_filename'],
            'equipment_id':             row['equipment_id'],
            'equipment_name':           row['equipment_name'],
            'category':                 row['category'],
            'due_label':                due_label,
            'is_overdue':               is_overdue,
            'days_out':                 days_out,
            'reminder_sent_at':         row['reminder_sent_at'],
            'second_reminder_sent_at':  row['second_reminder_sent_at'],
            'waitlist_count':           waitlist_counts.get(row['equipment_id'], 0),
        })

    from collections import OrderedDict
    groups = OrderedDict()
    for r in raw:
        key = (r['customer_name'].strip().lower(), r['member_number'].strip().lower())
        if key not in groups:
            groups[key] = {
                'id':                      r['id'],
                'customer_name':           r['customer_name'],
                'member_number':           r['member_number'],
                'phone':                   r['phone'],
                'checkout_notes':          r['checkout_notes'],
                'photo_filename':          r['photo_filename'],
                'is_overdue':              False,
                'days_out':                0,
                'reminder_sent_at':        None,
                'second_reminder_sent_at': None,
                'days_since_reminder':     0,
                'checkouts':               [],
            }
        g = groups[key]
        g['checkouts'].append(r)
        if r['is_overdue']:
            g['is_overdue'] = True
        if r['days_out'] > g['days_out']:
            g['days_out'] = r['days_out']
            g['id'] = r['id']
        if r['reminder_sent_at'] and (not g['reminder_sent_at'] or r['reminder_sent_at'] > g['reminder_sent_at']):
            g['reminder_sent_at'] = r['reminder_sent_at']
            g['days_since_reminder'] = (now_utc - datetime.fromisoformat(r['reminder_sent_at']).replace(tzinfo=timezone.utc)).total_seconds() / 86400
        if r['second_reminder_sent_at'] and (not g['second_reminder_sent_at'] or r['second_reminder_sent_at'] > g['second_reminder_sent_at']):
            g['second_reminder_sent_at'] = r['second_reminder_sent_at']

    active = list(groups.values())


    restring_stats = db.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status IN ('pending','complete')) AS active_jobs,
            COUNT(*) FILTER (WHERE status = 'pending')               AS needs_stringing,
            COUNT(*) FILTER (WHERE status = 'complete')              AS ready_pickup,
            COUNT(*) FILTER (WHERE status = 'complete'
                             AND completed_at < datetime('now', '-7 days')) AS overdue_pickup
        FROM restrings
    """).fetchone()

    flag_map = member_flags(db, [(g['customer_name'], g['member_number']) for g in active])
    for g in active:
        f = flag_map.get((g['customer_name'], g['member_number']), {'fn': False, 'fm': False})
        g['flag_name']   = f['fn']
        g['flag_number'] = f['fm']

    available_equipment = db.execute(
        """SELECT e.id, e.name, e.category FROM equipment e
           WHERE e.active = 1 AND e.under_maintenance = 0
           AND NOT EXISTS (
               SELECT 1 FROM checkouts c WHERE c.equipment_id = e.id AND c.returned_at IS NULL
           )
           ORDER BY e.category, e.name"""
    ).fetchall()

    from flask import session
    return render_template('admin/dashboard.html', active=active, q=q,
                           waitlist_members=waitlist_members,
                           staff_names=current_app.config.get('STAFF_NAMES', []),
                           current_staff=session.get('staff_name', ''),
                           restring_stats=restring_stats,
                           available_equipment=available_equipment)


@admin_bp.route('/quick-checkout', methods=['POST'])
@login_required
def quick_checkout():
    db = get_db()
    equipment_id = request.form.get('equipment_id', '').strip()
    name   = request.form.get('customer_name', '').strip()
    member = request.form.get('member_number', '').strip()
    phone  = format_phone(request.form.get('phone', '').strip())
    notes  = request.form.get('checkout_notes', '').strip()
    if not equipment_id or not name or not member:
        return redirect(url_for('admin.dashboard'))
    equipment_id = int(equipment_id)
    existing = db.execute(
        "SELECT id FROM checkouts WHERE equipment_id=? AND returned_at IS NULL", (equipment_id,)
    ).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO checkouts (equipment_id, customer_name, member_number, phone, checkout_notes) VALUES (?,?,?,?,?)",
            (equipment_id, name, member, phone or None, notes or None)
        )
        db.commit()
        sync_member_phone(db, member, phone)
        _log('quick_checkout', f'{name} ({member}) — equipment {equipment_id}')
    return redirect(url_for('admin.dashboard'))


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


@admin_bp.route('/checkout/<int:checkout_id>/edit', methods=['POST'])
@login_required
def checkout_edit(checkout_id):
    from database import format_phone
    db = get_db()
    name   = request.form.get('customer_name', '').strip()
    member = request.form.get('member_number', '').strip()
    phone  = format_phone(request.form.get('phone', '').strip()) or None
    notes  = request.form.get('checkout_notes', '').strip() or None
    if name and member:
        db.execute(
            "UPDATE checkouts SET customer_name=?, member_number=?, phone=?, checkout_notes=? WHERE id=?",
            (name, member, phone, notes, checkout_id)
        )
        _log('Edit Checkout', f"#{checkout_id} — {name}")
        db.commit()
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/return-multiple', methods=['POST'])
@login_required
def return_multiple():
    ids    = request.form.getlist('checkout_ids')
    notes  = request.form.get('notes', '').strip() or None
    db     = get_db()
    for cid in ids:
        db.execute(
            "UPDATE checkouts SET returned_at=datetime('now'), return_notes=? WHERE id=?",
            (notes, int(cid))
        )
    db.commit()
    return redirect(url_for('admin.dashboard'))


def _reminder_equipment_text(db, customer_name, member_number):
    """Return (phone, item_text, return_pronoun, all_ids) for all active checkouts by this member."""
    rows = db.execute(
        """SELECT c.id, c.phone, e.name AS equipment_name
           FROM checkouts c JOIN equipment e ON c.equipment_id = e.id
           WHERE c.customer_name=? AND c.member_number=? AND c.returned_at IS NULL
           ORDER BY c.checked_out_at ASC""",
        (customer_name, member_number)
    ).fetchall()
    if not rows:
        return None, None, None, []
    phone = rows[0]['phone']
    names = [r['equipment_name'] for r in rows]
    all_ids = [r['id'] for r in rows]
    if len(names) == 1:
        item_text = f"a {names[0]}"
        pronoun = "it"
    elif len(names) == 2:
        item_text = f"a {names[0]} and a {names[1]}"
        pronoun = "them"
    else:
        item_text = ', '.join(f"a {n}" for n in names[:-1]) + f", and a {names[-1]}"
        pronoun = "them"
    return phone, item_text, pronoun, all_ids


@admin_bp.route('/checkout/<int:checkout_id>/send-reminder', methods=['POST'])
@login_required
def checkout_send_reminder(checkout_id):
    db = get_db()
    member = db.execute(
        "SELECT customer_name, member_number FROM checkouts WHERE id=? AND returned_at IS NULL",
        (checkout_id,)
    ).fetchone()
    if not member:
        return redirect(url_for('admin.dashboard'))
    phone, item_text, pronoun, all_ids = _reminder_equipment_text(db, member['customer_name'], member['member_number'])
    if phone:
        from sms import send_sms
        send_sms(phone,
            f"Hello from the San Antonio Country Club Tennis Shop! "
            f"This is a friendly reminder that you currently have {item_text} checked out "
            f"that has been out for more than 3 days. Please return {pronoun} to the Tennis Shop at your earliest "
            f"convenience to avoid incurring any late fees.\n"
            f"If you have any questions, please call the Tennis Shop at 210-824-5951. Thank you!")
        for cid in all_ids:
            db.execute("UPDATE checkouts SET reminder_sent_at=datetime('now') WHERE id=?", (cid,))
        db.commit()
        _log('Demo Reminder Sent', f"{member['customer_name']} ({member['member_number']}) — {item_text}")
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/checkout/<int:checkout_id>/send-second-reminder', methods=['POST'])
@login_required
def checkout_send_second_reminder(checkout_id):
    db = get_db()
    member = db.execute(
        "SELECT customer_name, member_number FROM checkouts WHERE id=? AND returned_at IS NULL",
        (checkout_id,)
    ).fetchone()
    if not member:
        return redirect(url_for('admin.dashboard'))
    phone, item_text, pronoun, all_ids = _reminder_equipment_text(db, member['customer_name'], member['member_number'])
    if phone:
        oldest = db.execute(
            """SELECT MIN(checked_out_at) AS oldest_out FROM checkouts
               WHERE customer_name=? AND member_number=? AND returned_at IS NULL""",
            (member['customer_name'], member['member_number'])
        ).fetchone()
        from datetime import datetime, timezone
        days_out = int((datetime.now(timezone.utc) - datetime.fromisoformat(oldest['oldest_out']).replace(tzinfo=timezone.utc)).total_seconds() / 86400)
        from sms import send_sms
        send_sms(phone,
            f"Hello from the SACC Tennis Shop! This is a second reminder that you currently have "
            f"{item_text} checked out for {days_out} days. "
            f"Please return {pronoun} to the Tennis Shop at your earliest convenience. "
            f"Please note that demos checked out for more than 30 days will result in the member being charged the full price of the equipment. "
            f"If you have any questions, please call us at 210-824-5951. Thank you!")
        for cid in all_ids:
            db.execute("UPDATE checkouts SET second_reminder_sent_at=datetime('now') WHERE id=?", (cid,))
        db.commit()
        _log('Demo 2nd Reminder Sent', f"{member['customer_name']} ({member['member_number']}) — {item_text}")
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


@admin_bp.route('/non-members/search')
@login_required
def non_member_name_search():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        """SELECT customer_name, COUNT(*) AS job_count,
                  (SELECT phone FROM restrings r2
                   WHERE LOWER(r2.customer_name) = LOWER(restrings.customer_name)
                   AND r2.phone IS NOT NULL AND r2.phone != ''
                   ORDER BY r2.id DESC LIMIT 1) AS phone
           FROM restrings
           WHERE member_number = 'Non-member' AND LOWER(customer_name) LIKE LOWER(?)
           GROUP BY LOWER(customer_name)
           ORDER BY customer_name LIMIT 20""",
        (f'%{q}%',)
    ).fetchall()
    return jsonify([{'name': r['customer_name'], 'job_count': r['job_count'], 'phone': r['phone'] or ''} for r in rows])


@admin_bp.route('/members')
@login_required
def member_search_page():
    db = get_db()
    q  = request.args.get('q',  '').strip()
    qf = request.args.get('qf', '').strip()
    ql = request.args.get('ql', '').strip()
    rows = []

    def run_query(where, params):
        return db.execute(
            f'''SELECT mc.id, mc.member_name, mc.member_number, mc.email1, mc.email2, mc.phone1, mc.phone2, mc.notes,
                       (SELECT COUNT(*) FROM restrings r WHERE r.member_number = mc.member_number) AS restring_count
                FROM members_contact mc WHERE {where} ORDER BY mc.member_name''',
            params
        ).fetchall()

    if qf:
        # First-name search: "Last, FirstPrefix%" OR member number
        clauses = [f'member_name LIKE ?', 'member_number LIKE ?']
        rows = run_query(' OR '.join(clauses), [f'%, {qf}%', f'{qf}%'])
    elif ql:
        # Last-name search: "LastPrefix%" OR member number
        clauses = [f'member_name LIKE ?', 'member_number LIKE ?']
        rows = run_query(' OR '.join(clauses), [f'{ql}%', f'{ql}%'])
    elif q:
        name_patterns, number_pattern = _member_name_patterns(q)
        if name_patterns:
            or_clauses = ['member_name LIKE ?' for _ in name_patterns]
            params = list(name_patterns)
            if number_pattern:
                or_clauses.append('member_number LIKE ?')
                params.append(number_pattern)
            rows = run_query(' OR '.join(or_clauses), params)

    cleared = request.args.get('cleared') == '1'
    focus_ql = cleared or request.args.get('focus') == 'last'
    return render_template('admin/member_search.html', rows=rows, q=q, qf=qf, ql=ql, mode='members', cleared=cleared, focus_ql=focus_ql)


@admin_bp.route('/members/autocomplete')
@login_required
def member_autocomplete():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        '''SELECT id, member_name, member_number FROM members_contact
           WHERE member_name LIKE ? OR member_number LIKE ?
           ORDER BY member_name LIMIT 12''',
        (f'{q}%', f'{q}%')
    ).fetchall()
    return jsonify([{'id': r['id'], 'name': r['member_name'], 'number': r['member_number']} for r in rows])


@admin_bp.route('/non-members')
@login_required
def non_member_search():
    db = get_db()
    q = request.args.get('q', '').strip()
    rows = []
    if q:
        rows = db.execute(
            """SELECT customer_name,
                      COUNT(*) AS job_count,
                      MAX(date_in) AS last_seen,
                      GROUP_CONCAT(DISTINCT racquet) AS racquets
               FROM restrings
               WHERE member_number = 'Non-member'
                 AND customer_name LIKE ?
               GROUP BY LOWER(customer_name)
               ORDER BY customer_name""",
            (f'%{q}%',)
        ).fetchall()
    return render_template('admin/member_search.html', rows=rows, q=q, mode='non_members')


@admin_bp.route('/members/<int:member_id>/profile')
@login_required
def member_profile(member_id):
    db = get_db()
    member = db.execute(
        "SELECT * FROM members_contact WHERE id=?", (member_id,)
    ).fetchone()
    if not member:
        return redirect(url_for('admin.member_search_page'))
    restrings = db.execute(
        "SELECT * FROM restrings WHERE member_number=? ORDER BY date_in DESC",
        (member['member_number'],)
    ).fetchall()
    checkouts = db.execute(
        """SELECT c.*, e.name AS equipment_name, e.category,
                  ROUND(julianday(COALESCE(c.returned_at, datetime('now'))) - julianday(c.checked_out_at)) AS duration_days
           FROM checkouts c JOIN equipment e ON c.equipment_id = e.id
           WHERE c.member_number=? ORDER BY c.checked_out_at DESC""",
        (member['member_number'],)
    ).fetchall()
    back_kwargs = {k: v for k, v in [
        ('q',  request.args.get('back_q',  '')),
        ('qf', request.args.get('back_qf', '')),
        ('ql', request.args.get('back_ql', '')),
    ] if v}
    if back_kwargs:
        back_kwargs['cleared'] = '1'
    else:
        back_kwargs['focus'] = 'last'
    back_url = url_for('admin.member_search_page', **back_kwargs)
    return render_template('admin/member_profile.html',
                           member=member, restrings=restrings, checkouts=checkouts,
                           back_url=back_url)


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
    notes          = request.form.get('notes', '').strip() or None
    racquet_used   = request.form.get('racquet_used', '').strip() or None
    shoe_size      = request.form.get('shoe_size', '').strip() or None
    skirt_short_size = request.form.get('skirt_short_size', '').strip() or None
    hat_size       = request.form.get('hat_size', '').strip() or None
    clothing_brand = request.form.get('clothing_brand', '').strip() or None
    grip_size      = request.form.get('grip_size', '').strip() or None
    q              = request.form.get('q', '')
    if name and number:
        db.execute(
            """UPDATE members_contact SET member_name=?, member_number=?, email1=?, email2=?, phone1=?, phone2=?,
               notes=?, racquet_used=?, shoe_size=?, skirt_short_size=?, hat_size=?, clothing_brand=?, grip_size=? WHERE id=?""",
            (name, number, email1, email2, phone1, phone2, notes,
             racquet_used, shoe_size, skirt_short_size, hat_size, clothing_brand, grip_size, member_id)
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

    notes  = request.form.get('notes', '').strip() or None
    if name and number:
        try:
            db.execute("INSERT INTO members (member_name, member_number) VALUES (?, ?)", (name, number))
            db.execute(
                "INSERT INTO members_contact (member_name, member_number, email1, email2, phone1, phone2, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, number, email1, email2, phone1, phone2, notes)
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


@admin_bp.route('/guide')
@login_required
def guide():
    return render_template('admin/guide.html')


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

    turnaround = db.execute(
        """
        SELECT strung_by,
               COUNT(*) AS total_jobs,
               ROUND(AVG(julianday(completed_at) - julianday(date_in)), 1) AS avg_days,
               ROUND(MIN(julianday(completed_at) - julianday(date_in)), 1) AS min_days,
               ROUND(MAX(julianday(completed_at) - julianday(date_in)), 1) AS max_days
        FROM restrings
        WHERE status IN ('complete', 'picked_up')
          AND completed_at IS NOT NULL
          AND strung_by IS NOT NULL AND strung_by != ''
        GROUP BY strung_by
        ORDER BY total_jobs DESC
        """
    ).fetchall()

    return render_template('admin/reports.html', popular=popular, durations=durations, members=members, turnaround=turnaround)


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
        "SELECT id, name, category, qr_filename, notes FROM equipment WHERE active = 1 AND (notes IS NULL OR notes NOT LIKE '%DNC%') ORDER BY category, name"
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


@admin_bp.route('/roster')
@login_required
def roster():
    db = get_db()
    staff = db.execute("SELECT * FROM staff ORDER BY name ASC").fetchall()
    pin_error = request.args.get('pin_error') == '1'
    return render_template('admin/roster.html', staff=staff, pin_error=pin_error)


@admin_bp.route('/roster/add', methods=['POST'])
@login_required
def roster_add():
    name = request.form.get('name', '').strip()
    if name:
        db = get_db()
        try:
            db.execute("INSERT INTO staff (name) VALUES (?)", (name,))
            db.commit()
        except Exception:
            pass
    return redirect(url_for('admin.roster'))


@admin_bp.route('/roster/<int:staff_id>/remove', methods=['POST'])
@login_required
def roster_remove(staff_id):
    import config
    pin = request.form.get('pin', '').strip()
    if pin != config.RETIRE_PIN:
        return redirect(url_for('admin.roster', pin_error='1'))
    db = get_db()
    db.execute("DELETE FROM staff WHERE id=?", (staff_id,))
    db.commit()
    return redirect(url_for('admin.roster'))


@admin_bp.route('/lesson-slips', methods=['GET'])
@login_required
def lesson_slip_form():
    db = get_db()
    staff_names = [r['name'] for r in db.execute("SELECT name FROM staff ORDER BY name ASC").fetchall()]
    return render_template('admin/lesson_slip_form.html', staff_names=staff_names)


@admin_bp.route('/lesson-slips/print', methods=['POST'])
@login_required
def lesson_slip_print():
    data = {
        'lesson_date':     request.form.get('lesson_date', ''),
        'lesson_name':     request.form.get('lesson_name', ''),
        'pro_name':        request.form.get('pro_name', ''),
        'lesson_category': request.form.get('lesson_category', ''),
        'lesson_duration': request.form.get('lesson_duration', ''),
        'other_text':      request.form.get('other_text', ''),
        'amount':          request.form.get('amount', ''),
        'notes':           request.form.get('notes', ''),
        'green_paper':     request.form.get('green_paper') == '1',
    }
    return render_template('admin/lesson_slip_print.html', data=data)
