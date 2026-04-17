CREATE TABLE IF NOT EXISTS equipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    spec1_label TEXT, spec1_value TEXT,
    spec2_label TEXT, spec2_value TEXT,
    spec3_label TEXT, spec3_value TEXT,
    spec4_label TEXT, spec4_value TEXT,
    notes       TEXT,
    qr_filename TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkouts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id   INTEGER NOT NULL REFERENCES equipment(id),
    customer_name  TEXT NOT NULL,
    member_number  TEXT NOT NULL,
    checked_out_at TEXT NOT NULL DEFAULT (datetime('now')),
    returned_at    TEXT,
    return_notes   TEXT
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
    notes         TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_restrings_status ON restrings(status);
