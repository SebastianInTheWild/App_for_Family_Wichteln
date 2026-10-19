"""SQLite-Zugriff und Verschlüsselung der Wichtel-Paare."""
import json
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

import default_templates

DATA_DIR = Path(os.environ.get("WICHTEL_DATA_DIR", Path(__file__).parent / "data"))
DB_PATH = DATA_DIR / "wichteln.db"
KEY_PATH = DATA_DIR / "secret.key"

KINDS = ("mail", "reminder")

# Frühere Standardtexte (vor den Vorlagen-Listen) – nur für die Übernahme alter Datenbanken
OLD_DEFAULTS = {
    "mail": ("Wichteln {jahr}: Dein Wichtelpartner steht fest!",
             "Hallo {name},\n\ndie Auslosung für unser Wichteln {jahr} ist erfolgt.\n\n"
             "Du beschenkst dieses Jahr: {partner}\n\nBitte verrate es niemandem!\n\n"
             "Viele Grüße\nEuer Wichtel-Orga-Team\n"),
    "reminder": ("Erinnerung: Wichteln {jahr}",
                 "Hallo {name},\n\nkleine Erinnerung: Beim Wichteln {jahr} beschenkst du {partner}.\n"
                 "Hast du schon ein Geschenk besorgt?\n\nViele Grüße\nEuer Wichtel-Orga-Team\n"),
}

SCHEMA = """
-- Wichtelrunden (z. B. je Familie); alles außer Vorlagen und Einstellungen gehört zu einer Runde
CREATE TABLE IF NOT EXISTS groups (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,
    lookback_years INTEGER NOT NULL DEFAULT 1
);
-- E-Mail ist je Runde eindeutig; dieselbe Person kann in mehreren Runden mitmachen
CREATE TABLE IF NOT EXISTS participants (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    email    TEXT NOT NULL,
    UNIQUE (group_id, email)
);
-- Symmetrische Haushalts-Matrix: gespeichert wird nur (a, b) mit a < b
CREATE TABLE IF NOT EXISTS households (
    a INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    b INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    PRIMARY KEY (a, b),
    CHECK (a < b)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Ein Datensatz pro Paar, Inhalt (Schenker -> Beschenkter) Fernet-verschlüsselt
CREATE TABLE IF NOT EXISTS draws (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL DEFAULT 1,
    year       INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    token      BLOB NOT NULL
);
-- Geplante Aufgaben: kind = 'draw' (auslosen + senden) oder 'reminder'
CREATE TABLE IF NOT EXISTS jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL DEFAULT 1,
    kind     TEXT NOT NULL CHECK (kind IN ('draw', 'reminder')),
    year     INTEGER NOT NULL,
    run_at   TEXT NOT NULL,                -- lokale Zeit, 'YYYY-MM-DDTHH:MM'
    status   TEXT NOT NULL DEFAULT 'pending',
    message  TEXT,
    rule_id  INTEGER                       -- gesetzt, wenn aus einer Jahresregel erzeugt
);
-- Jährlich wiederkehrende Termine, aus denen der Zeitplan jedes Jahr einen Job erzeugt
CREATE TABLE IF NOT EXISTS rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL DEFAULT 1,
    kind       TEXT NOT NULL CHECK (kind IN ('draw', 'reminder')),
    mode       TEXT NOT NULL CHECK (mode IN ('nth_weekday', 'fixed_date', 'advent')),
    month      INTEGER,
    nth        INTEGER,
    weekday    INTEGER,
    day        INTEGER,
    time       TEXT NOT NULL,              -- 'HH:MM'
    created_at TEXT NOT NULL               -- lokale Zeit; frühere Termine werden nicht nachgeholt
);
-- E-Mail-Vorlagen; beim Versand wird je Empfänger zufällig eine aktive Vorlage gewählt
CREATE TABLE IF NOT EXISTS templates (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind    TEXT NOT NULL CHECK (kind IN ('mail', 'reminder')),
    title   TEXT NOT NULL,
    subject TEXT NOT NULL,
    body    TEXT NOT NULL,
    active  INTEGER NOT NULL DEFAULT 1
);
"""


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db():
    conn = connect()
    conn.execute("PRAGMA foreign_keys = OFF")  # für den Tabellen-Umbau alter Datenbanken
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS draws_group_year ON draws(group_id, year);
            CREATE UNIQUE INDEX IF NOT EXISTS jobs_rule_year
                ON jobs(rule_id, year) WHERE rule_id IS NOT NULL;
        """)
        if not conn.execute("SELECT 1 FROM groups").fetchone():
            conn.execute("INSERT INTO groups (id, name) VALUES (1, 'Familie')")
        if not conn.execute("SELECT 1 FROM templates").fetchone():
            for kind, items in default_templates.DEFAULTS.items():
                for t in items:
                    add_template(conn, kind, t["title"], t["subject"], t["body"])
        conn.commit()
    finally:
        conn.close()


def _migrate(conn):
    """Bringt Datenbanken älterer Versionen auf den aktuellen Stand."""
    if "group_id" not in _columns(conn, "participants"):
        # E-Mail war global eindeutig -> Tabelle neu aufbauen (IDs bleiben, Haushalte passen weiter)
        conn.executescript("""
            CREATE TABLE participants_new (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                name     TEXT NOT NULL,
                email    TEXT NOT NULL,
                UNIQUE (group_id, email)
            );
            INSERT INTO participants_new (id, group_id, name, email)
                SELECT id, 1, name, email FROM participants;
            DROP TABLE participants;
            ALTER TABLE participants_new RENAME TO participants;
        """)
    for table in ("draws", "jobs", "rules"):
        if "group_id" not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN group_id INTEGER NOT NULL DEFAULT 1")
    if "rule_id" not in _columns(conn, "jobs"):
        conn.execute("ALTER TABLE jobs ADD COLUMN rule_id INTEGER")

    lookback = get_setting(conn, "lookback_years")
    if lookback is not None:
        if not conn.execute("SELECT 1 FROM groups").fetchone():
            conn.execute("INSERT INTO groups (id, name, lookback_years) VALUES (1, 'Familie', ?)",
                         (int(lookback),))
        conn.execute("DELETE FROM settings WHERE key = 'lookback_years'")

    # Einzelne Texte aus alten Versionen: selbst geänderte als eigene Vorlage übernehmen
    for kind in KINDS:
        subject, body = get_setting(conn, f"{kind}_subject"), get_setting(conn, f"{kind}_body")
        if subject is None:
            continue
        if (subject, body) != OLD_DEFAULTS[kind]:
            if not conn.execute("SELECT 1 FROM templates").fetchone():
                for k, items in default_templates.DEFAULTS.items():
                    for t in items:
                        add_template(conn, k, t["title"], t["subject"], t["body"])
            add_template(conn, kind, "Eigene Vorlage", subject, body)
        conn.execute("DELETE FROM settings WHERE key IN (?, ?)", (f"{kind}_subject", f"{kind}_body"))


# --- Schlüssel ---------------------------------------------------------------

def _fernet():
    key = os.environ.get("WICHTEL_KEY")
    if not key:
        if not KEY_PATH.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            KEY_PATH.write_bytes(Fernet.generate_key())
        key = KEY_PATH.read_bytes()
    return Fernet(key)


def encrypt_text(text):
    return _fernet().encrypt(text.encode()).decode()


def decrypt_text(token):
    return _fernet().decrypt(token.encode()).decode()


# --- Runden ------------------------------------------------------------------

def list_groups(conn):
    return conn.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM participants p WHERE p.group_id = g.id) AS people, "
        "(SELECT COUNT(DISTINCT year) FROM draws d WHERE d.group_id = g.id) AS draws "
        "FROM groups g ORDER BY g.name COLLATE NOCASE").fetchall()


def get_group(conn, gid):
    return conn.execute("SELECT * FROM groups WHERE id = ?", (gid,)).fetchone()


def add_group(conn, name):
    return conn.execute("INSERT INTO groups (name) VALUES (?)", (name.strip(),)).lastrowid


def rename_group(conn, gid, name):
    conn.execute("UPDATE groups SET name = ? WHERE id = ?", (name.strip(), gid))


def set_lookback(conn, gid, years):
    conn.execute("UPDATE groups SET lookback_years = ? WHERE id = ?", (years, gid))


def delete_group(conn, gid):
    for table in ("draws", "jobs", "rules"):
        conn.execute(f"DELETE FROM {table} WHERE group_id = ?", (gid,))
    conn.execute("DELETE FROM groups WHERE id = ?", (gid,))  # Teilnehmer + Haushalte per CASCADE


# --- Teilnehmer --------------------------------------------------------------

def list_participants(conn, gid):
    return conn.execute("SELECT * FROM participants WHERE group_id = ? "
                        "ORDER BY name COLLATE NOCASE", (gid,)).fetchall()


def add_participant(conn, gid, name, email):
    conn.execute("INSERT INTO participants (group_id, name, email) VALUES (?, ?, ?)",
                 (gid, name.strip(), email.strip().lower()))


def import_participants(conn, gid, people):
    """people: Liste von (name, email). Gibt (neu, übersprungen) zurück; vorhandene E-Mails
    (auch doppelte innerhalb der Liste) werden übersprungen."""
    added = 0
    for name, email in people:
        added += conn.execute("INSERT OR IGNORE INTO participants (group_id, name, email) "
                              "VALUES (?, ?, ?)", (gid, name.strip(), email.strip().lower())).rowcount
    return added, len(people) - added


def copy_participants(conn, from_gid, to_gid):
    """Übernimmt Teilnehmer einer anderen Runde; bereits vorhandene E-Mails bleiben unverändert."""
    return conn.execute("INSERT OR IGNORE INTO participants (group_id, name, email) "
                        "SELECT ?, name, email FROM participants WHERE group_id = ?",
                        (to_gid, from_gid)).rowcount


def delete_participant(conn, gid, pid):
    conn.execute("DELETE FROM participants WHERE id = ? AND group_id = ?", (pid, gid))


# --- Haushalte ---------------------------------------------------------------

def household_pairs(conn, gid):
    return {(r["a"], r["b"]) for r in conn.execute(
        "SELECT h.a, h.b FROM households h JOIN participants p ON p.id = h.a "
        "WHERE p.group_id = ?", (gid,))}


def save_households(conn, gid, pairs):
    ids = {r["id"] for r in list_participants(conn, gid)}
    conn.execute("DELETE FROM households WHERE a IN "
                 "(SELECT id FROM participants WHERE group_id = ?)", (gid,))
    conn.executemany("INSERT INTO households (a, b) VALUES (?, ?)",
                     [(min(a, b), max(a, b)) for a, b in pairs
                      if a != b and a in ids and b in ids])


# --- Einstellungen -----------------------------------------------------------

def get_setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# --- Vorlagen ----------------------------------------------------------------

def list_templates(conn, kind):
    return conn.execute("SELECT * FROM templates WHERE kind = ? ORDER BY id", (kind,)).fetchall()


def active_templates(conn, kind):
    return conn.execute("SELECT * FROM templates WHERE kind = ? AND active = 1 ORDER BY id",
                        (kind,)).fetchall()


def add_template(conn, kind, title, subject, body, active=True):
    return conn.execute("INSERT INTO templates (kind, title, subject, body, active) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (kind, title, subject, body, 1 if active else 0)).lastrowid


def update_template(conn, tid, title, subject, body, active):
    conn.execute("UPDATE templates SET title = ?, subject = ?, body = ?, active = ? WHERE id = ?",
                 (title, subject, body, 1 if active else 0, tid))


def delete_template(conn, tid):
    conn.execute("DELETE FROM templates WHERE id = ?", (tid,))


# --- Auslosungen (verschlüsselt) ---------------------------------------------

def save_draw(conn, gid, year, pairs):
    """pairs: Liste von (giver_email, receiver_email)."""
    f = _fernet()
    conn.execute("DELETE FROM draws WHERE group_id = ? AND year = ?", (gid, year))
    conn.executemany(
        "INSERT INTO draws (group_id, year, token) VALUES (?, ?, ?)",
        [(gid, year, f.encrypt(json.dumps([g, r]).encode())) for g, r in pairs],
    )


def load_draws(conn, gid, years):
    """Entschlüsselt die Paare der angegebenen Jahre einer Runde."""
    years = list(years)
    if not years:
        return set()
    f = _fernet()
    marks = ",".join("?" * len(years))
    rows = conn.execute(f"SELECT token FROM draws WHERE group_id = ? AND year IN ({marks})",
                        [gid, *years])
    return {tuple(json.loads(f.decrypt(r["token"]))) for r in rows}


def draw_overview(conn, gid):
    return conn.execute(
        "SELECT year, COUNT(*) AS pairs, MAX(created_at) AS created_at FROM draws "
        "WHERE group_id = ? GROUP BY year ORDER BY year DESC", (gid,)).fetchall()


def delete_draw(conn, gid, year):
    conn.execute("DELETE FROM draws WHERE group_id = ? AND year = ?", (gid, year))


# --- Zeitplan ----------------------------------------------------------------

def list_jobs(conn, gid):
    return conn.execute("SELECT * FROM jobs WHERE group_id = ? ORDER BY run_at DESC",
                        (gid,)).fetchall()


def add_job(conn, gid, kind, year, run_at):
    conn.execute("INSERT INTO jobs (group_id, kind, year, run_at) VALUES (?, ?, ?, ?)",
                 (gid, kind, year, run_at))


def delete_job(conn, gid, job_id):
    """Einmalige Jobs werden gelöscht. Jobs aus einer Regel werden nur als übersprungen
    markiert, sonst würde der Zeitplan sie für dieses Jahr gleich wieder anlegen."""
    conn.execute("UPDATE jobs SET status = 'skipped', message = 'Für dieses Jahr ausgesetzt' "
                 "WHERE id = ? AND group_id = ? AND rule_id IS NOT NULL AND status = 'pending'",
                 (job_id, gid))
    conn.execute("DELETE FROM jobs WHERE id = ? AND group_id = ? AND rule_id IS NULL",
                 (job_id, gid))


def list_rules(conn, gid=None):
    if gid is None:
        return conn.execute("SELECT * FROM rules ORDER BY id").fetchall()
    return conn.execute("SELECT * FROM rules WHERE group_id = ? ORDER BY kind, id",
                        (gid,)).fetchall()


def add_rule(conn, gid, kind, mode, month, nth, weekday, day, time, created_at):
    conn.execute("INSERT INTO rules (group_id, kind, mode, month, nth, weekday, day, time, "
                 "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (gid, kind, mode, month, nth, weekday, day, time, created_at))


def delete_rule(conn, gid, rule_id):
    conn.execute("DELETE FROM jobs WHERE rule_id = ? AND group_id = ? AND status = 'pending'",
                 (rule_id, gid))
    conn.execute("DELETE FROM rules WHERE id = ? AND group_id = ?", (rule_id, gid))


def add_rule_job(conn, rule, year, run_at):
    """Legt den Job einer Regel für ein Jahr an – höchstens einmal pro Regel und Jahr."""
    conn.execute("INSERT OR IGNORE INTO jobs (group_id, kind, year, run_at, rule_id) "
                 "VALUES (?, ?, ?, ?, ?)",
                 (rule["group_id"], rule["kind"], year, run_at, rule["id"]))


def claim_due_jobs(conn, now):
    """Markiert fällige Jobs als 'running' – atomar, damit kein Job doppelt läuft."""
    claimed = []
    due = conn.execute("SELECT * FROM jobs WHERE status = 'pending' AND run_at <= ? "
                       "ORDER BY run_at", (now,)).fetchall()
    for job in due:
        cur = conn.execute("UPDATE jobs SET status = 'running' "
                           "WHERE id = ? AND status = 'pending'", (job["id"],))
        if cur.rowcount:
            claimed.append(job)
    conn.commit()
    return claimed


def finish_job(conn, job_id, status, message):
    conn.execute("UPDATE jobs SET status = ?, message = ? WHERE id = ?",
                 (status, message, job_id))
