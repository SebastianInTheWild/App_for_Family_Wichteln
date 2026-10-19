"""SQLite-Zugriff und Verschlüsselung der Wichtel-Paare."""
import json
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

DATA_DIR = Path(os.environ.get("WICHTEL_DATA_DIR", Path(__file__).parent / "data"))
DB_PATH = DATA_DIR / "wichteln.db"
KEY_PATH = DATA_DIR / "secret.key"

DEFAULT_SUBJECT = "Wichteln {jahr}: Dein Wichtelpartner steht fest!"
DEFAULT_BODY = """Hallo {name},

die Auslosung für unser Wichteln {jahr} ist erfolgt.

Du beschenkst dieses Jahr: {partner}

Bitte verrate es niemandem!

Viele Grüße
Euer Wichtel-Orga-Team
"""
DEFAULT_REMINDER_SUBJECT = "Erinnerung: Wichteln {jahr}"
DEFAULT_REMINDER_BODY = """Hallo {name},

kleine Erinnerung: Beim Wichteln {jahr} beschenkst du {partner}.
Hast du schon ein Geschenk besorgt?

Viele Grüße
Euer Wichtel-Orga-Team
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL,
    email  TEXT NOT NULL UNIQUE
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
    year       INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    token      BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS draws_year ON draws(year);
-- Geplante Aufgaben: kind = 'draw' (auslosen + senden) oder 'reminder'
CREATE TABLE IF NOT EXISTS jobs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
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
    kind       TEXT NOT NULL CHECK (kind IN ('draw', 'reminder')),
    mode       TEXT NOT NULL CHECK (mode IN ('nth_weekday', 'fixed_date', 'advent')),
    month      INTEGER,
    nth        INTEGER,
    weekday    INTEGER,
    day        INTEGER,
    time       TEXT NOT NULL,              -- 'HH:MM'
    created_at TEXT NOT NULL               -- lokale Zeit; frühere Termine werden nicht nachgeholt
);
"""


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        if "rule_id" not in {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}:
            conn.execute("ALTER TABLE jobs ADD COLUMN rule_id INTEGER")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS jobs_rule_year "
                     "ON jobs(rule_id, year) WHERE rule_id IS NOT NULL")
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('mail_subject', ?)", (DEFAULT_SUBJECT,))
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('mail_body', ?)", (DEFAULT_BODY,))
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('reminder_subject', ?)",
                     (DEFAULT_REMINDER_SUBJECT,))
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('reminder_body', ?)",
                     (DEFAULT_REMINDER_BODY,))
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('lookback_years', '1')")


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


# --- Teilnehmer --------------------------------------------------------------

def list_participants(conn):
    return conn.execute("SELECT * FROM participants ORDER BY name COLLATE NOCASE").fetchall()


def add_participant(conn, name, email):
    conn.execute("INSERT INTO participants (name, email) VALUES (?, ?)",
                 (name.strip(), email.strip().lower()))


def delete_participant(conn, pid):
    conn.execute("DELETE FROM participants WHERE id = ?", (pid,))


# --- Haushalte ---------------------------------------------------------------

def household_pairs(conn):
    return {(r["a"], r["b"]) for r in conn.execute("SELECT a, b FROM households")}


def save_households(conn, pairs):
    conn.execute("DELETE FROM households")
    conn.executemany("INSERT INTO households (a, b) VALUES (?, ?)",
                     [(min(a, b), max(a, b)) for a, b in pairs if a != b])


# --- Einstellungen -----------------------------------------------------------

def get_setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# --- Auslosungen (verschlüsselt) ---------------------------------------------

def save_draw(conn, year, pairs):
    """pairs: Liste von (giver_email, receiver_email)."""
    f = _fernet()
    conn.execute("DELETE FROM draws WHERE year = ?", (year,))
    conn.executemany(
        "INSERT INTO draws (year, token) VALUES (?, ?)",
        [(year, f.encrypt(json.dumps([g, r]).encode())) for g, r in pairs],
    )


def load_draws(conn, years):
    """Entschlüsselt die Paare der angegebenen Jahre – nur für die Sperrprüfung."""
    if not years:
        return set()
    f = _fernet()
    marks = ",".join("?" * len(years))
    rows = conn.execute(f"SELECT token FROM draws WHERE year IN ({marks})", list(years))
    return {tuple(json.loads(f.decrypt(r["token"]))) for r in rows}


def draw_overview(conn):
    return conn.execute(
        "SELECT year, COUNT(*) AS pairs, MAX(created_at) AS created_at "
        "FROM draws GROUP BY year ORDER BY year DESC").fetchall()


def delete_draw(conn, year):
    conn.execute("DELETE FROM draws WHERE year = ?", (year,))


# --- Zeitplan ----------------------------------------------------------------

def list_jobs(conn):
    return conn.execute("SELECT * FROM jobs ORDER BY run_at DESC").fetchall()


def add_job(conn, kind, year, run_at):
    conn.execute("INSERT INTO jobs (kind, year, run_at) VALUES (?, ?, ?)", (kind, year, run_at))


def delete_job(conn, job_id):
    """Einmalige Jobs werden gelöscht. Jobs aus einer Regel werden nur als übersprungen
    markiert, sonst würde der Zeitplan sie für dieses Jahr gleich wieder anlegen."""
    conn.execute("UPDATE jobs SET status = 'skipped', message = 'Für dieses Jahr ausgesetzt' "
                 "WHERE id = ? AND rule_id IS NOT NULL AND status = 'pending'", (job_id,))
    conn.execute("DELETE FROM jobs WHERE id = ? AND rule_id IS NULL", (job_id,))


def list_rules(conn):
    return conn.execute("SELECT * FROM rules ORDER BY kind, id").fetchall()


def add_rule(conn, kind, mode, month, nth, weekday, day, time, created_at):
    conn.execute("INSERT INTO rules (kind, mode, month, nth, weekday, day, time, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (kind, mode, month, nth, weekday, day, time, created_at))


def delete_rule(conn, rule_id):
    conn.execute("DELETE FROM jobs WHERE rule_id = ? AND status = 'pending'", (rule_id,))
    conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


def add_rule_job(conn, rule_id, kind, year, run_at):
    """Legt den Job einer Regel für ein Jahr an – höchstens einmal pro Regel und Jahr."""
    conn.execute("INSERT OR IGNORE INTO jobs (kind, year, run_at, rule_id) VALUES (?, ?, ?, ?)",
                 (kind, year, run_at, rule_id))


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
