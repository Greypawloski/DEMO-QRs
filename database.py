import re
import sqlite3
import click
from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DB_PATH'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))


@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Database initialized.')


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def format_phone(phone):
    """Format a phone string as XXX-XXX-XXXX for 10-digit US numbers; pass others through unchanged."""
    if not phone:
        return phone
    d = re.sub(r'\D', '', phone)
    if len(d) == 10:
        return f'{d[:3]}-{d[3:6]}-{d[6:]}'
    return phone


def sync_member_phone(db, member_number, submitted_phone):
    """Update members_contact phone fields when a new phone is submitted during checkout/restring."""
    if not member_number or member_number == 'Non-member' or not submitted_phone:
        return

    def digits(s):
        return re.sub(r'\D', '', s or '')

    submitted_digits = digits(submitted_phone)
    if not submitted_digits:
        return

    row = db.execute(
        "SELECT id, phone1, phone2 FROM members_contact WHERE member_number = ?",
        (member_number,)
    ).fetchone()
    if not row:
        return  # member not in imported roster — skip

    p1_digits = digits(row['phone1'])
    p2_digits = digits(row['phone2'])

    if submitted_digits == p1_digits or submitted_digits == p2_digits:
        return  # already recorded

    formatted = format_phone(submitted_phone)
    if not p1_digits:
        db.execute("UPDATE members_contact SET phone1 = ? WHERE id = ?", (formatted, row['id']))
    else:
        db.execute("UPDATE members_contact SET phone2 = ? WHERE id = ?", (formatted, row['id']))
    db.commit()
