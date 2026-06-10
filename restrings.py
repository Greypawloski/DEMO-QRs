import io
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, request, redirect, url_for, send_file, current_app
from database import get_db, sync_member_phone, format_phone, member_flags
from auth import login_required

_CENTRAL = ZoneInfo('America/Chicago')

def _fmt_central(dt_str):
    if not dt_str:
        return ''
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    return dt.astimezone(_CENTRAL).strftime('%-m/%-d/%Y %-I:%M %p')

restrings_bp = Blueprint('restrings', __name__, url_prefix='/admin/restrings')


def _back_to_list():
    """Redirect to the restring list, staying on the pending-only view if that's where the action came from."""
    ref = request.referrer or ''
    if 'view=pending' in ref:
        return redirect(url_for('restrings.list_restrings', view='pending'))
    return redirect(url_for('restrings.list_restrings'))


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
           WHERE member_number = ? AND status = 'picked_up'
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


@restrings_bp.route('/racquet-suggest')
@login_required
def racquet_suggest():
    from flask import jsonify
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT racquet FROM restrings WHERE LOWER(racquet) LIKE LOWER(?) ORDER BY racquet LIMIT 12",
        (f'%{q}%',)
    ).fetchall()
    return jsonify([r[0] for r in rows])


@restrings_bp.route('/string-stock-check')
@login_required
def string_stock_check():
    from flask import jsonify
    q = request.args.get('q', '').strip()
    if len(q) < 3:
        return jsonify({'in_stock': True, 'match': None})
    db = get_db()
    rows = db.execute('SELECT brand, model FROM strings_stock').fetchall()
    stock = [(r['brand'].lower(), r['model'].lower()) for r in rows]

    def check_one(s):
        s = s.strip().lower()
        if len(s) < 3:
            return True
        for brand, model in stock:
            full = brand + ' ' + model
            if s == full or s == model or s in full or model in s:
                return True
        return False

    parts = [p for p in q.split('/') if p.strip()]
    not_found = [p.strip() for p in parts if not check_one(p)]

    if not_found:
        return jsonify({'in_stock': False, 'not_found': not_found})
    return jsonify({'in_stock': True, 'match': None})


@restrings_bp.route('/string-suggest')
@login_required
def string_suggest():
    from flask import jsonify
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT string FROM restrings WHERE LOWER(string) LIKE LOWER(?) ORDER BY string LIMIT 12",
        (f'%{q}%',)
    ).fetchall()
    return jsonify([r[0] for r in rows])


@restrings_bp.route('/non-member-history')
@login_required
def non_member_restring_history():
    from flask import jsonify
    name = request.args.get('name', '').strip()
    if not name:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        """SELECT racquet, string, tension, date_in
           FROM restrings
           WHERE member_number = 'Non-member' AND LOWER(customer_name) = LOWER(?) AND status = 'picked_up'
           ORDER BY id DESC
           LIMIT 10""",
        (name,)
    ).fetchall()
    return jsonify([{
        'racquet': r['racquet'],
        'string':  r['string'],
        'tension': r['tension'],
        'date_in': r['date_in'],
    } for r in rows])


def _list_context(q='', qb='', view=''):
    """Build the full template context for restrings_list.html."""
    db = get_db()

    # view=pending: only jobs not yet strung (excludes Ready), no picked-up section
    where_pending   = "status = 'pending'" if view == 'pending' else "status != 'picked_up'"
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
        f"SELECT * FROM restrings WHERE {where_pending} ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, date_promised ASC",
        params_pending
    ).fetchall()
    if view == 'pending':
        completed = []
    else:
        where_completed += " AND date(COALESCE(picked_up_at, date_in)) >= date('now', '-7 days')"
        completed = db.execute(
            f"SELECT * FROM restrings WHERE {where_completed} ORDER BY COALESCE(picked_up_at, date_in) DESC",
            params_completed
        ).fetchall()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today_central = datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d')
    stats = {
        'pending':    db.execute("SELECT COUNT(*) FROM restrings WHERE status='pending'").fetchone()[0],
        'ready':      db.execute("SELECT COUNT(*) FROM restrings WHERE status='complete'").fetchone()[0],
        'this_month': db.execute("SELECT COUNT(*) FROM restrings WHERE strftime('%Y-%m', date_in) = strftime('%Y-%m', 'now')").fetchone()[0],
        'today':      db.execute("SELECT COUNT(*) FROM restrings WHERE date_in = ?", (today_central,)).fetchone()[0],
    }
    overdue_ids = {r['id'] for r in db.execute(
        "SELECT id FROM restrings WHERE status='complete' AND completed_at < datetime('now', '-7 days')"
    ).fetchall()}
    stringer_names = [r[0] for r in db.execute(
        "SELECT DISTINCT strung_by FROM restrings WHERE strung_by IS NOT NULL AND strung_by != '' ORDER BY strung_by"
    ).fetchall()]
    staff_names = [r['name'] for r in db.execute("SELECT name FROM staff ORDER BY name ASC").fetchall()]
    flag_data = member_flags(db, [(r['customer_name'], r['member_number']) for r in pending])
    mflags = {}
    for r in pending:
        f = flag_data.get((r['customer_name'], r['member_number']), {'fn': False, 'fm': False})
        mflags[r['id']] = f

    from collections import OrderedDict

    def _ckey(r):
        digits = ''.join(c for c in (r['phone'] or '') if c.isdigit())
        return digits if len(digits) >= 10 else r['customer_name'].strip().lower()

    grp_map = OrderedDict()
    for r in pending:
        grp_map.setdefault(_ckey(r), []).append(r)
    pending_groups = list(grp_map.values())

    return dict(pending=pending, pending_groups=pending_groups, completed=completed,
                q=q, qb=qb, view=view, stats=stats, overdue_ids=overdue_ids,
                stringer_names=stringer_names, staff_names=staff_names, mflags=mflags)


@restrings_bp.route('/')
@login_required
def list_restrings():
    q  = request.args.get('q',  '').strip()
    qb = request.args.get('qb', '').strip()
    view = 'pending' if request.args.get('view') == 'pending' else ''
    return render_template('admin/restrings_list.html', **_list_context(q, qb, view))


@restrings_bp.route('/new', methods=['GET', 'POST'])
@login_required
def restring_new():
    if request.method == 'POST':
        db = get_db()
        member = 'Non-member' if request.form.get('non_member') == '1' else request.form.get('member_number', '').strip()
        phone = format_phone(request.form.get('phone', '').strip())
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
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()
        sync_member_phone(db, member, phone)
        return redirect(url_for('restrings.restring_print_slip', restring_id=new_id))
    prefill = {
        'member_number': request.args.get('member_number', ''),
        'customer_name': request.args.get('customer_name', ''),
        'phone':         request.args.get('phone', ''),
    }
    staff_names = [r['name'] for r in get_db().execute("SELECT name FROM staff ORDER BY name ASC").fetchall()]
    return render_template('admin/restring_form.html', item=None, prefill=prefill,
                           staff_names=staff_names)


@restrings_bp.route('/<int:restring_id>/edit', methods=['GET', 'POST'])
@login_required
def restring_edit(restring_id):
    db = get_db()
    item = db.execute("SELECT * FROM restrings WHERE id = ?", (restring_id,)).fetchone()
    if item is None:
        return _back_to_list()

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
        if request.form.get('mark_ready') == '1' and item['status'] == 'pending':
            from flask import session as flask_session
            db.execute(
                "UPDATE restrings SET status='complete', completed_at=datetime('now') WHERE id=?",
                (restring_id,)
            )
            staff = flask_session.get('staff_name', 'Unknown')
            customer_name = request.form['customer_name'].strip()
            racquet = request.form['racquet'].strip()
            db.execute(
                "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
                (staff, 'Marked Restring Ready', f"{customer_name} — {racquet}")
            )
            db.commit()
            sync_member_phone(db, member, phone)
            no_sms = bool(request.form.get('no_sms'))
            if phone and not no_sms:
                from sms import send_sms
                send_sms(phone,
                         f"Hi {customer_name.split()[0]}, your racquet is ready for pickup at the SACC Tennis Shop. "
                         f"Please stop by during business hours. Reply STOP to opt out.")
            return _back_to_list()
        db.commit()
        sync_member_phone(db, member, phone)
        return _back_to_list()
    staff_names = [r['name'] for r in get_db().execute("SELECT name FROM staff ORDER BY name ASC").fetchall()]
    return render_template('admin/restring_form.html', item=item,
                           staff_names=staff_names)


@restrings_bp.route('/<int:restring_id>/delete', methods=['POST'])
@login_required
def restring_delete(restring_id):
    from flask import session, current_app
    db = get_db()
    job = db.execute("SELECT customer_name, racquet, status FROM restrings WHERE id=?", (restring_id,)).fetchone()
    if job is None:
        return _back_to_list()
    pin = request.form.get('pin', '')
    from flask import current_app
    if pin != current_app.config.get('RETIRE_PIN', ''):
        view = 'pending' if 'view=pending' in (request.referrer or '') else ''
        return render_template('admin/restrings_list.html', **_list_context(view=view),
                               delete_pin_error=True,
                               delete_pin_error_id=restring_id,
                               delete_pin_error_name=f"{job['customer_name']} — {job['racquet']}")
    db.execute("DELETE FROM restrings WHERE id=?", (restring_id,))
    staff = session.get('staff_name', 'Unknown')
    db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
               (staff, 'Delete Restring', f"{job['customer_name']} — {job['racquet']}"))
    db.commit()
    return _back_to_list()


@restrings_bp.route('/bulk-mark-ready', methods=['POST'])
@login_required
def bulk_mark_ready():
    from flask import session
    ids_raw = request.form.get('ids', '')
    ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    if not ids:
        return _back_to_list()
    db = get_db()
    placeholders = ','.join('?' * len(ids))
    jobs = db.execute(
        f"SELECT * FROM restrings WHERE id IN ({placeholders}) AND status='pending'",
        ids
    ).fetchall()
    if not jobs:
        return _back_to_list()

    staff = session.get('staff_name', 'Unknown')
    for job in jobs:
        db.execute(
            "UPDATE restrings SET status='complete', completed_at=datetime('now') WHERE id=?",
            (job['id'],)
        )
        db.execute(
            "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
            (staff, 'Marked Restring Ready', f"{job['customer_name']} — {job['racquet']}")
        )

    phone = next((j['phone'] for j in jobs if j['phone']), None)
    no_sms = all(j['no_sms'] for j in jobs)
    if phone and not no_sms:
        first_name = jobs[0]['customer_name'].split()[0]
        racquets = [j['racquet'] for j in jobs]
        count = len(racquets)
        if count == 1:
            r_phrase = f"your {racquets[0]} is"
        elif len(set(r.lower() for r in racquets)) == 1:
            r_phrase = f"your {count} {racquets[0]} racquets are"
        elif count == 2:
            r_phrase = f"your {racquets[0]} and {racquets[1]} are"
        else:
            r_phrase = f"your {count} racquets are"
        from sms import send_sms
        send_sms(phone,
                 f"Hi {first_name}, {r_phrase} ready for pickup at the SACC Tennis Shop. "
                 f"Please stop by during business hours. Reply STOP to opt out.")

    db.commit()
    return _back_to_list()


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
    return _back_to_list()


@restrings_bp.route('/<int:restring_id>/undo-pickup', methods=['POST'])
@login_required
def restring_undo_pickup(restring_id):
    from flask import session
    db = get_db()
    job = db.execute("SELECT customer_name, racquet FROM restrings WHERE id=?", (restring_id,)).fetchone()
    db.execute("UPDATE restrings SET status='complete', picked_up_at=NULL WHERE id=?", (restring_id,))
    if job:
        staff = session.get('staff_name', 'Unknown')
        db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
                   (staff, 'Undo Pickup', f"{job['customer_name']} — {job['racquet']}"))
    db.commit()
    return _back_to_list()


@restrings_bp.route('/<int:restring_id>/update-billing', methods=['POST'])
@login_required
def restring_update_billing(restring_id):
    db = get_db()
    receipt            = request.form.get('receipt', '').strip()
    charged            = request.form.get('charged', '').strip()
    additional_charges = request.form.get('additional_charges', '').strip()
    db.execute(
        "UPDATE restrings SET receipt=?, charged=?, additional_charges=? WHERE id=?",
        (receipt or None, charged or None, additional_charges or None, restring_id)
    )
    db.commit()
    return redirect(url_for('restrings.restrings_history_view'))


@restrings_bp.route('/<int:restring_id>/update-date', methods=['POST'])
@login_required
def restring_update_date(restring_id):
    db = get_db()
    new_date_in   = request.form.get('date_in', '').strip()
    new_completed = request.form.get('completed_at', '').strip()
    if new_date_in:
        db.execute("UPDATE restrings SET date_in=? WHERE id=?", (new_date_in, restring_id))
    if new_completed:
        db.execute("UPDATE restrings SET completed_at=? WHERE id=?", (new_completed, restring_id))
    if new_date_in or new_completed:
        db.commit()
    return redirect(url_for('restrings.restrings_history_view'))


@restrings_bp.route('/<int:restring_id>/history-delete', methods=['POST'])
@login_required
def restring_history_delete(restring_id):
    from flask import current_app, session
    db = get_db()
    job = db.execute("SELECT customer_name, racquet FROM restrings WHERE id=?", (restring_id,)).fetchone()
    if not job:
        return redirect(url_for('restrings.restrings_history_view'))
    if request.form.get('pin') != current_app.config.get('RETIRE_PIN', ''):
        return redirect(url_for('restrings.restrings_history_view',
                                pin_error_id=restring_id,
                                pin_error_name=f"{job['customer_name']} — {job['racquet']}"))
    db.execute("DELETE FROM restrings WHERE id=?", (restring_id,))
    staff = session.get('staff_name', 'Unknown')
    db.execute("INSERT INTO activity_log (staff_name, action, details) VALUES (?,?,?)",
               (staff, 'delete_history', f"Deleted restring #{restring_id}: {job['customer_name']} — {job['racquet']}"))
    db.commit()
    return redirect(url_for('restrings.restrings_history_view'))


@restrings_bp.route('/stringer-report')
@login_required
def stringer_report():
    from datetime import date
    from collections import OrderedDict
    db = get_db()
    current_ym = date.today().strftime('%Y-%m')
    rows = db.execute("""
        SELECT strftime('%Y-%m', completed_at) AS ym,
               strung_by,
               COUNT(*) AS job_count
        FROM restrings
        WHERE status IN ('complete','picked_up')
          AND strung_by IS NOT NULL AND strung_by != ''
          AND completed_at IS NOT NULL
          AND strftime('%Y-%m', completed_at) >= '2026-04'
          AND strftime('%Y-%m', completed_at) < ?
        GROUP BY ym, strung_by
        ORDER BY ym DESC, job_count DESC
    """, (current_ym,)).fetchall()
    months = OrderedDict()
    for r in rows:
        months.setdefault(r['ym'], []).append({'name': r['strung_by'], 'jobs': r['job_count']})
    return render_template('admin/stringer_report.html', months=months)


@restrings_bp.route('/history')
@login_required
def restrings_history_view():
    db = get_db()
    months = db.execute(
        "SELECT DISTINCT substr(date_in,1,7) AS ym FROM restrings WHERE status IN ('complete','picked_up') ORDER BY ym DESC"
    ).fetchall()
    month_list = [r['ym'] for r in months]
    qall  = request.args.get('qall',  '').strip()
    qallb = request.args.get('qallb', '').strip()
    if qall or qallb:
        sql = "SELECT * FROM restrings WHERE status IN ('complete','picked_up')"
        params = []
        if qall:
            sql += " AND (customer_name LIKE ? OR member_number LIKE ?)"
            params += [f'%{qall}%', f'%{qall}%']
        if qallb:
            sql += " AND strung_by LIKE ?"
            params.append(f'%{qallb}%')
        sql += " ORDER BY date_in DESC"
        rows = db.execute(sql, params).fetchall()
        return render_template('admin/restrings_history.html', rows=rows, months=month_list, selected='',
                               pin_error_id=None, pin_error_name='')
    selected = request.args.get('ym', month_list[0] if month_list else '')
    q  = request.args.get('q',  '').strip()
    qs = request.args.get('qs', '').strip()
    sql  = "SELECT * FROM restrings WHERE status IN ('complete','picked_up') AND substr(date_in,1,7)=?"
    params = [selected]
    if q:
        sql += " AND (customer_name LIKE ? OR member_number LIKE ?)"
        params += [f'%{q}%', f'%{q}%']
    if qs:
        sql += " AND strung_by LIKE ?"
        params.append(f'%{qs}%')
    sql += " ORDER BY date_in DESC"
    rows = db.execute(sql, params).fetchall() if selected else []
    return render_template('admin/restrings_history.html', rows=rows, months=month_list, selected=selected,
                           pin_error_id=request.args.get('pin_error_id'),
                           pin_error_name=request.args.get('pin_error_name', ''))


@restrings_bp.route('/export-csv')
@login_required
def restrings_export_csv():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM restrings WHERE status IN ('complete','picked_up') ORDER BY created_at DESC"
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
    elif new_status == 'picked_up':
        db.execute("UPDATE restrings SET status=?, picked_up_at=datetime('now') WHERE id=?",
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
    return _back_to_list()


@restrings_bp.route('/<int:restring_id>/print-slip')
@login_required
def restring_print_slip(restring_id):
    db = get_db()
    job = db.execute("SELECT * FROM restrings WHERE id=?", (restring_id,)).fetchone()
    if job is None:
        return _back_to_list()
    return render_template('admin/restring_print_slip.html', job=job)


@restrings_bp.route('/<int:restring_id>/send-pickup-reminder', methods=['POST'])
@login_required
def restring_send_pickup_reminder(restring_id):
    from flask import session
    db = get_db()
    job = db.execute(
        "SELECT customer_name, phone, racquet, no_sms FROM restrings WHERE id=? AND status='complete'",
        (restring_id,)
    ).fetchone()
    if job and job['phone'] and not job['no_sms']:
        from sms import send_sms
        send_sms(job['phone'],
            f"Hi! Just a friendly reminder from the SACC Tennis Shop that your {job['racquet']} "
            f"is ready for pickup — it's been waiting for you for over a week. We hope to see you soon!")
        db.execute("UPDATE restrings SET pickup_reminder_sent_at=datetime('now') WHERE id=?", (restring_id,))
        staff = session.get('staff_name', 'Unknown')
        db.execute(
            "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
            (staff, 'Pickup Reminder Sent', f"{job['customer_name']} — {job['racquet']}")
        )
        db.commit()
    return _back_to_list()


@restrings_bp.route('/<int:restring_id>/mark-notified', methods=['POST'])
@login_required
def restring_mark_notified(restring_id):
    from flask import session
    db = get_db()
    job = db.execute(
        "SELECT customer_name, racquet FROM restrings WHERE id=? AND status='complete'",
        (restring_id,)
    ).fetchone()
    if job:
        db.execute("UPDATE restrings SET pickup_reminder_sent_at=datetime('now') WHERE id=?", (restring_id,))
        staff = session.get('staff_name', 'Unknown')
        db.execute(
            "INSERT INTO activity_log (staff_name, action, details) VALUES (?, ?, ?)",
            (staff, 'Marked Notified (In Person/Phone)', f"{job['customer_name']} — {job['racquet']}")
        )
        db.commit()
    return _back_to_list()


@restrings_bp.route('/<int:restring_id>/string-label')
@login_required
def restring_string_label(restring_id):
    db = get_db()
    job = db.execute("SELECT * FROM restrings WHERE id=?", (restring_id,)).fetchone()
    if job is None:
        return _back_to_list()
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
        return _back_to_list()
    db = get_db()
    db.execute(f"UPDATE restrings SET {field}=? WHERE id=?", (value or None, restring_id))
    db.commit()
    return redirect(url_for('restrings.list_restrings') + f'#job-{restring_id}')


@restrings_bp.route('/string-stock', methods=['GET'])
@login_required
def string_stock():
    db = get_db()
    strings = db.execute(
        'SELECT id, brand, model, string_type, color, gauges FROM strings_stock ORDER BY brand, model'
    ).fetchall()
    return render_template('admin/strings_stock.html', strings=strings,
                           pin_error_id=None, pin_error_name=None)


@restrings_bp.route('/string-stock/add', methods=['POST'])
@login_required
def string_stock_add():
    brand       = request.form.get('brand', '').strip()
    model       = request.form.get('model', '').strip()
    string_type = request.form.get('string_type', '').strip()
    color       = request.form.get('color', '').strip()
    gauges      = request.form.get('gauges', '').strip()
    if brand and model:
        db = get_db()
        db.execute(
            'INSERT INTO strings_stock (brand, model, string_type, color, gauges) VALUES (?,?,?,?,?)',
            (brand, model, string_type, color, gauges)
        )
        db.commit()
    return redirect(url_for('restrings.string_stock'))


@restrings_bp.route('/string-stock/<int:stock_id>/delete', methods=['POST'])
@login_required
def string_stock_delete(stock_id):
    from flask import current_app
    db = get_db()
    row = db.execute('SELECT id, brand, model FROM strings_stock WHERE id = ?', (stock_id,)).fetchone()
    if not row:
        return redirect(url_for('restrings.string_stock'))
    if request.form.get('pin') != current_app.config['RETIRE_PIN']:
        strings = db.execute(
            'SELECT id, brand, model, string_type, color, gauges FROM strings_stock ORDER BY brand, model'
        ).fetchall()
        return render_template('admin/strings_stock.html', strings=strings,
                               pin_error_id=stock_id,
                               pin_error_name=row['brand'] + ' ' + row['model'])
    db.execute('DELETE FROM strings_stock WHERE id = ?', (stock_id,))
    db.commit()
    return redirect(url_for('restrings.string_stock'))
