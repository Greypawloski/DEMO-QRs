import io
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, request, redirect, url_for, send_file
from database import get_db, sync_member_phone, format_phone
from auth import login_required

_CENTRAL = ZoneInfo('America/Chicago')

def _fmt_central(dt_str):
    if not dt_str:
        return ''
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    return dt.astimezone(_CENTRAL).strftime('%-m/%-d/%Y %-I:%M %p')

restrings_bp = Blueprint('restrings', __name__, url_prefix='/admin/restrings')


@restrings_bp.route('/member-history')
@login_required
def member_restring_history():
    from flask import jsonify
    member_number = request.args.get('member_number', '').strip()
    if not member_number or member_number == 'Non-member':
        return jsonify([])
    db = get_db()
    rows = db.execute(
        """SELECT racquet, string, tension, date_in
           FROM restrings
           WHERE member_number = ?
           ORDER BY id DESC
           LIMIT 10""",
        (member_number,)
    ).fetchall()
    return jsonify([{
        'racquet': r['racquet'],
        'string':  r['string'],
        'tension': r['tension'],
        'date_in': r['date_in'],
    } for r in rows])


@restrings_bp.route('/')
@login_required
def list_restrings():
    db = get_db()
    q  = request.args.get('q',  '').strip()
    qb = request.args.get('qb', '').strip()

    where_pending   = "status != 'picked_up'"
    where_completed = "status = 'picked_up'"
    params_pending   = []
    params_completed = []

    if q:
        pattern = f'%{q}%'
        where_pending   += " AND (customer_name LIKE ? OR member_number LIKE ?)"
        where_completed += " AND (customer_name LIKE ? OR member_number LIKE ?)"
        params_pending   += [pattern, pattern]
        params_completed += [pattern, pattern]

    if qb:
        pattern_b = f'%{qb}%'
        where_pending   += " AND strung_by LIKE ?"
        where_completed += " AND strung_by LIKE ?"
        params_pending   += [pattern_b]
        params_completed += [pattern_b]

    pending = db.execute(
        f"SELECT * FROM restrings WHERE {where_pending} ORDER BY date_promised ASC",
        params_pending
    ).fetchall()
    where_completed += " AND date(created_at) >= date('now', '-7 days')"
    completed = db.execute(
        f"SELECT * FROM restrings WHERE {where_completed} ORDER BY created_at DESC",
        params_completed
    ).fetchall()
    stats = {
        'pending':    db.execute("SELECT COUNT(*) FROM restrings WHERE status='pending'").fetchone()[0],
        'ready':      db.execute("SELECT COUNT(*) FROM restrings WHERE status='complete'").fetchone()[0],
        'this_month': db.execute("SELECT COUNT(*) FROM restrings WHERE strftime('%Y-%m', date_in) = strftime('%Y-%m', 'now')").fetchone()[0],
    }
    overdue_ids = {r['id'] for r in db.execute(
        "SELECT id FROM restrings WHERE status='complete' AND completed_at < datetime('now', '-7 days')"
    ).fetchall()}
    return render_template('admin/restrings_list.html', pending=pending, completed=completed, q=q, qb=qb, stats=stats, overdue_ids=overdue_ids)


@restrings_bp.route('/new', methods=['GET', 'POST'])
@login_required
def restring_new():
    if request.method == 'POST':
        db = get_db()
        member = 'Non-member' if request.form.get('non_member') == '1' else request.form.get('member_number', '').strip()
        phone = format_phone(request.form.get('phone', '').strip())
        if member and member != 'Non-member' and not request.form.get('confirmed'):
            dup = db.execute(
                "SELECT id, racquet, status FROM restrings WHERE member_number=? AND status != 'picked_up' LIMIT 1",
                (member,)
            ).fetchone()
            if dup:
                return render_template('admin/restring_form.html', item=None,
                                       dup_warning=dup, prefill=request.form)
        db.execute(
            """
            INSERT INTO restrings
              (date_in, customer_name, phone, member_number, racquet,
               string, tension, date_promised, receipt, charged, additional_charges, notes, strung_by, customer_own_string, no_sms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.form['date_in'],
                request.form['customer_name'].strip(),
                phone,
                member,
                request.form['racquet'].strip(),
                request.form['string'].strip(),
                request.form['tension'].strip(),
                request.form['date_promised'],
                request.form.get('receipt', '').strip(),
                request.form.get('charged', '').strip(),
                request.form.get('additional_charges', '').strip(),
                request.form.get('notes', '').strip(),
                request.form.get('strung_by', '').strip(),
                1 if request.form.get('customer_own_string') else 0,
                1 if request.form.get('no_sms') else 0,
            )
        )
        db.commit()
        sync_member_phone(db, member, phone)
        return redirect(url_for('restrings.list_restrings'))
    return render_template('admin/restring_form.html', item=None)


@restrings_bp.route('/<int:restring_id>/edit', methods=['GET', 'POST'])
@login_required
def restring_edit(restring_id):
    db = get_db()
    item = db.execute("SELECT * FROM restrings WHERE id = ?", (restring_id,)).fetchone()
    if item is None:
        return redirect(url_for('restrings.list_restrings'))

    if request.method == 'POST':
        member = 'Non-member' if request.form.get('non_member') == '1' else request.form.get('member_number', '').strip()
        phone = format_phone(request.form.get('phone', '').strip())
        db.execute(
            """
            UPDATE restrings SET
              date_in=?, customer_name=?, phone=?, member_number=?, racquet=?,
              string=?, tension=?, date_promised=?, receipt=?, charged=?, additional_charges=?, notes=?, strung_by=?, customer_own_string=?, no_sms=?
            WHERE id=?
            """,
            (
                request.form['date_in'],
                request.form['customer_name'].strip(),
                phone,
                member,
                request.form['racquet'].strip(),
                request.form['string'].strip(),
                request.form['tension'].strip(),
                request.form['date_promised'],
                request.form.get('receipt', '').strip(),
                request.form.get('charged', '').strip(),
                request.form.get('additional_charges', '').strip(),
                request.form.get('notes', '').strip(),
                request.form.get('strung_by', '').strip(),
                1 if request.form.get('customer_own_string') else 0,
                1 if request.form.get('no_sms') else 0,
                restring_id,
            )
        )
        db.commit()
        sync_member_phone(db, member, phone)
        return redirect(url_for('restrings.list_restrings'))
    return render_template('admin/restring_form.html', item=item)


@restrings_bp.route('/<int:restring_id>/delete', methods=['POST'])
@login_required
def restring_delete(restring_id):
    from flask import session, current_app
    db = get_db()
    job = db.execute("SELECT customer_name, racquet, status FROM restrings WHERE id=?", (restring_id,)).fetchone()
    if job is None:
        return redirect(url_for('restrings.list_restrings'))
    pin = request.form.get('pin', '')
    from flask import current_app
    if pin != current_app.config.get('RETIRE_PIN', ''):
        pending = db.execute("SELECT * FROM restrings WHERE status != 'picked_up' ORDER BY date_promised ASC").fetchall()
        completed = db.execute("SELECT * FROM restrings WHERE status = 'picked_up' ORDER BY created_at DESC").fetchall()
        return render_template('admin/restrings_list.html', pending=pending, completed=completed,
                               q='', qb='', delete_pin_error=True,
                               delete_pin_error_id=restring_id,
                               delete_pin_error_name=f"{job['customer_name']} — {job['racquet']}")
    db.execute("DELETE FROM restrings WHERE id=?", (restring_id,))
    staff = session.get('staff_name', 'Unknown')
    db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
               (staff, 'Delete Restring', f"{job['customer_name']} — {job['racquet']}"))
    db.commit()
    return redirect(url_for('restrings.list_restrings'))


@restrings_bp.route('/<int:restring_id>/unmark-ready', methods=['POST'])
@login_required
def restring_unmark_ready(restring_id):
    from flask import session
    db = get_db()
    job = db.execute("SELECT customer_name, racquet FROM restrings WHERE id=?", (restring_id,)).fetchone()
    db.execute("UPDATE restrings SET status='pending', completed_at=NULL WHERE id=?", (restring_id,))
    if job:
        staff = session.get('staff_name', 'Unknown')
        db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
                   (staff, 'Unmark Restring Ready', f"{job['customer_name']} — {job['racquet']}"))
    db.commit()
    return redirect(url_for('restrings.list_restrings'))


@restrings_bp.route('/<int:restring_id>/undo-pickup', methods=['POST'])
@login_required
def restring_undo_pickup(restring_id):
    from flask import session
    db = get_db()
    job = db.execute("SELECT customer_name, racquet FROM restrings WHERE id=?", (restring_id,)).fetchone()
    db.execute("UPDATE restrings SET status='complete' WHERE id=?", (restring_id,))
    if job:
        staff = session.get('staff_name', 'Unknown')
        db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
                   (staff, 'Undo Pickup', f"{job['customer_name']} — {job['racquet']}"))
    db.commit()
    return redirect(url_for('restrings.list_restrings'))


@restrings_bp.route('/<int:restring_id>/update-date', methods=['POST'])
@login_required
def restring_update_date(restring_id):
    new_date = request.form.get('date_in', '').strip()
    if new_date:
        db = get_db()
        db.execute("UPDATE restrings SET date_in=? WHERE id=?", (new_date, restring_id))
        db.commit()
    return redirect(url_for('restrings.restrings_history_view'))


@restrings_bp.route('/history')
@login_required
def restrings_history_view():
    db = get_db()
    months = db.execute(
        "SELECT DISTINCT substr(date_in,1,7) AS ym FROM restrings WHERE status='picked_up' ORDER BY ym DESC"
    ).fetchall()
    month_list = [r['ym'] for r in months]
    qall  = request.args.get('qall',  '').strip()
    qallb = request.args.get('qallb', '').strip()
    if qall or qallb:
        sql = "SELECT * FROM restrings WHERE status='picked_up'"
        params = []
        if qall:
            sql += " AND (customer_name LIKE ? OR member_number LIKE ?)"
            params += [f'%{qall}%', f'%{qall}%']
        if qallb:
            sql += " AND strung_by LIKE ?"
            params.append(f'%{qallb}%')
        sql += " ORDER BY date_in DESC"
        rows = db.execute(sql, params).fetchall()
        return render_template('admin/restrings_history.html', rows=rows, months=month_list, selected='')
    selected = request.args.get('ym', month_list[0] if month_list else '')
    q  = request.args.get('q',  '').strip()
    qs = request.args.get('qs', '').strip()
    sql  = "SELECT * FROM restrings WHERE status='picked_up' AND substr(date_in,1,7)=?"
    params = [selected]
    if q:
        sql += " AND (customer_name LIKE ? OR member_number LIKE ?)"
        params += [f'%{q}%', f'%{q}%']
    if qs:
        sql += " AND strung_by LIKE ?"
        params.append(f'%{qs}%')
    sql += " ORDER BY date_in DESC"
    rows = db.execute(sql, params).fetchall() if selected else []
    return render_template('admin/restrings_history.html', rows=rows, months=month_list, selected=selected)


@restrings_bp.route('/export-csv')
@login_required
def restrings_export_csv():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM restrings WHERE status = 'picked_up' ORDER BY created_at DESC"
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Name', 'Racquet', 'String', 'Tension', 'Stringer', 'Date', 'Chit Number', 'Total', 'Additional Charges'])
    for r in rows:
        w.writerow([r['customer_name'], r['racquet'], r['string'], r['tension'],
                    r['strung_by'] or '', r['date_in'],
                    r['receipt'] or '', r['charged'] or '',
                    r['additional_charges'] or ''])
    buf.seek(0)
    return send_file(io.BytesIO(buf.getvalue().encode()),
                     as_attachment=True, download_name='stringing-history.csv',
                     mimetype='text/csv')


@restrings_bp.route('/<int:restring_id>/status', methods=['POST'])
@login_required
def restring_status(restring_id):
    from flask import session
    new_status = request.form.get('status', 'pending')
    db = get_db()
    job = db.execute("SELECT customer_name, racquet, phone, no_sms FROM restrings WHERE id=?", (restring_id,)).fetchone()
    if new_status == 'complete':
        db.execute("UPDATE restrings SET status=?, completed_at=datetime('now') WHERE id=?",
                   (new_status, restring_id))
    else:
        db.execute("UPDATE restrings SET status=? WHERE id=?", (new_status, restring_id))
    if job:
        staff = session.get('staff_name', 'Unknown')
        label = 'Marked Restring Ready' if new_status == 'complete' else 'Marked Restring Picked Up'
        db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
                   (staff, label, f"{job['customer_name']} — {job['racquet']}"))
        if new_status == 'complete' and job['phone'] and not job['no_sms']:
            from sms import send_sms
            send_sms(job['phone'],
                     f"Hi {job['customer_name'].split()[0]}, your racquet is ready for pickup at the SACC Tennis Shop. "
                     f"Please stop by during business hours. Reply STOP to opt out.")
    db.commit()
    return redirect(url_for('restrings.list_restrings'))


@restrings_bp.route('/<int:restring_id>/string-label')
@login_required
def restring_string_label(restring_id):
    db = get_db()
    job = db.execute("SELECT * FROM restrings WHERE id=?", (restring_id,)).fetchone()
    if job is None:
        return redirect(url_for('restrings.list_restrings'))
    from qr_utils import generate_string_label, LABEL_DIR
    filename = generate_string_label(
        restring_id,
        job['customer_name'],
        job['string'],
        job['tension'],
        job['strung_by'],
        job['completed_at'],
    )
    safe_name = job['customer_name'].replace(' ', '_')
    return send_file(str(LABEL_DIR / filename), as_attachment=True,
                     download_name=f"{safe_name}_string_label.png",
                     mimetype='image/png')


@restrings_bp.route('/<int:restring_id>/quick-update', methods=['POST'])
@login_required
def restring_quick_update(restring_id):
    field = request.form.get('field')
    value = request.form.get('value', '').strip()
    if field not in ('strung_by', 'receipt', 'charged', 'additional_charges'):
        return redirect(url_for('restrings.list_restrings'))
    db = get_db()
    db.execute(f"UPDATE restrings SET {field}=? WHERE id=?", (value or None, restring_id))
    db.commit()
    return redirect(url_for('restrings.list_restrings'))
