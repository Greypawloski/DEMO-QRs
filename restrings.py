from flask import Blueprint, render_template, request, redirect, url_for
from database import get_db
from auth import login_required

restrings_bp = Blueprint('restrings', __name__, url_prefix='/admin/restrings')


@restrings_bp.route('/')
@login_required
def list_restrings():
    db = get_db()
    pending = db.execute(
        "SELECT * FROM restrings WHERE status != 'picked_up' ORDER BY date_promised ASC"
    ).fetchall()
    completed = db.execute(
        "SELECT * FROM restrings WHERE status = 'picked_up' ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    return render_template('admin/restrings_list.html', pending=pending, completed=completed)


@restrings_bp.route('/new', methods=['GET', 'POST'])
@login_required
def restring_new():
    if request.method == 'POST':
        db = get_db()
        db.execute(
            """
            INSERT INTO restrings
              (date_in, customer_name, phone, member_number, racquet,
               string, tension, date_promised, receipt, charged, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.form['date_in'],
                request.form['customer_name'].strip(),
                request.form['phone'].strip(),
                request.form.get('member_number', '').strip(),
                request.form['racquet'].strip(),
                request.form['string'].strip(),
                request.form['tension'].strip(),
                request.form['date_promised'],
                request.form.get('receipt', '').strip(),
                request.form.get('charged', '').strip(),
                request.form.get('notes', '').strip(),
            )
        )
        db.commit()
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
        db.execute(
            """
            UPDATE restrings SET
              date_in=?, customer_name=?, phone=?, member_number=?, racquet=?,
              string=?, tension=?, date_promised=?, receipt=?, charged=?, notes=?
            WHERE id=?
            """,
            (
                request.form['date_in'],
                request.form['customer_name'].strip(),
                request.form['phone'].strip(),
                request.form.get('member_number', '').strip(),
                request.form['racquet'].strip(),
                request.form['string'].strip(),
                request.form['tension'].strip(),
                request.form['date_promised'],
                request.form.get('receipt', '').strip(),
                request.form.get('charged', '').strip(),
                request.form.get('notes', '').strip(),
                restring_id,
            )
        )
        db.commit()
        return redirect(url_for('restrings.list_restrings'))
    return render_template('admin/restring_form.html', item=item)


@restrings_bp.route('/<int:restring_id>/status', methods=['POST'])
@login_required
def restring_status(restring_id):
    new_status = request.form.get('status', 'pending')
    db = get_db()
    db.execute("UPDATE restrings SET status=? WHERE id=?", (new_status, restring_id))
    db.commit()
    return redirect(url_for('restrings.list_restrings'))
