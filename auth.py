from functools import wraps
from flask import session, redirect, url_for, request, render_template, current_app, Blueprint

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == current_app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        error = 'Incorrect password.'
    return render_template('admin/login.html', error=error)


@auth_bp.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('auth.login'))
