CREATE TABLE IF NOT EXISTS equipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    spec1_label TEXT, spec1_value TEXT,
    spec2_label TEXT, spec2_value TEXT,
    spec3_label TEXT, spec3_value TEXT,
    spec4_label TEXT, spec4_value TEXT,
    spec5_label TEXT, spec5_value TEXT,
    notes       TEXT,
    qr_filename TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    under_maintenance INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkouts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id   INTEGER NOT NULL REFERENCES equipment(id),
    customer_name  TEXT NOT NULL,
    member_number  TEXT NOT NULL,
    phone          TEXT,
    checked_out_at TEXT NOT NULL DEFAULT (datetime('now')),
    returned_at    TEXT,
    return_notes   TEXT,
    photo_filename TEXT,
    checkout_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_checkouts_equipment ON checkouts(equipment_id);
CREATE INDEX IF NOT EXISTS idx_checkouts_returned  ON checkouts(returned_at);

CREATE TABLE IF NOT EXISTS restrings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date_in       TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    phone         TEXT NOT NULL,
    member_number TEXT,
    racquet       TEXT NOT NULL,
    string        TEXT NOT NULL,
    tension       TEXT NOT NULL,
    date_promised TEXT NOT NULL,
    receipt       TEXT,
    charged       TEXT,
    additional_charges TEXT,
    customer_own_string INTEGER NOT NULL DEFAULT 0,
    notes         TEXT,
    strung_by     TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    completed_at  TEXT,
    no_sms        INTEGER NOT NULL DEFAULT 0,
    reminded_at   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_restrings_status ON restrings(status);

CREATE TABLE IF NOT EXISTS waitlist (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id  INTEGER NOT NULL REFERENCES equipment(id),
    customer_name TEXT NOT NULL,
    member_number TEXT NOT NULL,
    phone         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_waitlist_equipment ON waitlist(equipment_id);

CREATE TABLE IF NOT EXISTS members (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_name   TEXT NOT NULL,
    member_number TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_members_name   ON members(member_name);
CREATE INDEX IF NOT EXISTS idx_members_number ON members(member_number);

CREATE TABLE IF NOT EXISTS members_contact (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_name   TEXT NOT NULL,
    member_number TEXT NOT NULL UNIQUE,
    email1        TEXT,
    email2        TEXT,
    phone1        TEXT,
    phone2        TEXT,
    notes         TEXT,
    racquet_used  TEXT,
    shoe_size     TEXT,
    skirt_short_size TEXT,
    hat_size      TEXT,
    clothing_brand TEXT
);

CREATE INDEX IF NOT EXISTS idx_members_contact_name   ON members_contact(member_name);
CREATE INDEX IF NOT EXISTS idx_members_contact_number ON members_contact(member_number);

CREATE TABLE IF NOT EXISTS staff (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_name TEXT NOT NULL,
    action     TEXT NOT NULL,
    details    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
