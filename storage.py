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
    lookback_years INTEGER NOT NULL DEFAULT 1,
    mail_name      TEXT                    -- Anzeige in der Mail (Kopf + {gruppe}); leer = name
);
-- Zentrale Personenliste; die E-Mail identifiziert eine Person über Runden und Jahre
CREATE TABLE IF NOT EXISTS persons (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);
-- Teilnahme einer Person an einer Runde (Haushalte verweisen auf diese ID)
CREATE TABLE IF NOT EXISTS participants (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id  INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    UNIQUE (group_id, person_id)
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
    columns = _columns(conn, "participants")
    if "email" in columns:
        # Früher standen Name/E-Mail direkt bei der Teilnahme (anfangs ohne Runden).
        # -> zentrale Personenliste (gleiche E-Mail = eine Person, erster Name gewinnt);
        #    Teilnahme-IDs bleiben, damit die Haushalte weiter passen.
        group = "group_id" if "group_id" in columns else "1"
        conn.executescript(f"""
            INSERT OR IGNORE INTO persons (name, email)
                SELECT name, lower(email) FROM participants ORDER BY id;
            CREATE TABLE participants_new (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id  INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                UNIQUE (group_id, person_id)
            );
            INSERT OR IGNORE INTO participants_new (id, group_id, person_id)
                SELECT p.id, {group}, s.id FROM participants p
                JOIN persons s ON s.email = lower(p.email) ORDER BY p.id;
            DROP TABLE participants;
            ALTER TABLE participants_new RENAME TO participants;
        """)
    for table in ("draws", "jobs", "rules"):
        if "group_id" not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN group_id INTEGER NOT NULL DEFAULT 1")
    if "rule_id" not in _columns(conn, "jobs"):
        conn.execute("ALTER TABLE jobs ADD COLUMN rule_id INTEGER")
    if "mail_name" not in _columns(conn, "groups"):
        conn.execute("ALTER TABLE groups ADD COLUMN mail_name TEXT")

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
        if (_norm(subject), _norm(body)) != OLD_DEFAULTS[kind]:
            if not conn.execute("SELECT 1 FROM templates").fetchone():
                for k, items in default_templates.DEFAULTS.items():
                    for t in items:
                        add_template(conn, k, t["title"], t["subject"], t["body"])
            add_template(conn, kind, "Eigene Vorlage", subject, body)
        conn.execute("DELETE FROM settings WHERE key IN (?, ?)", (f"{kind}_subject", f"{kind}_body"))

    # Bis 8fd362a wurden alte Standardtexte mit Windows-Zeilenumbrüchen fälschlich übernommen
    for t in conn.execute("SELECT * FROM templates WHERE title = 'Eigene Vorlage'").fetchall():
        if (_norm(t["subject"]), _norm(t["body"])) == OLD_DEFAULTS[t["kind"]]:
            conn.execute("DELETE FROM templates WHERE id = ?", (t["id"],))


def _norm(text):
    """Browser schicken Textfelder mit \r\n – gespeichert wird einheitlich \n."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


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


def add_group(conn, name, mail_name=""):
    return conn.execute("INSERT INTO groups (name, mail_name) VALUES (?, ?)",
                        (name.strip(), mail_name.strip() or None)).lastrowid


def update_group(conn, gid, name, mail_name):
    conn.execute("UPDATE groups SET name = ?, mail_name = ? WHERE id = ?",
                 (name.strip(), mail_name.strip() or None, gid))


def set_lookback(conn, gid, years):
    conn.execute("UPDATE groups SET lookback_years = ? WHERE id = ?", (years, gid))


def delete_group(conn, gid):
    for table in ("draws", "jobs", "rules"):
        conn.execute(f"DELETE FROM {table} WHERE group_id = ?", (gid,))
    conn.execute("DELETE FROM groups WHERE id = ?", (gid,))  # Teilnehmer + Haushalte per CASCADE


# --- Teilnehmer --------------------------------------------------------------

def list_persons(conn):
    """Alle Personen mit der Menge ihrer Runden (groups: set von Runden-IDs)."""
    rows = conn.execute(
        "SELECT s.*, group_concat(p.group_id) AS gids FROM persons s "
        "LEFT JOIN participants p ON p.person_id = s.id "
        "GROUP BY s.id ORDER BY s.name COLLATE NOCASE").fetchall()
    return [{**dict(r), "groups": {int(x) for x in (r["gids"] or "").split(",") if x}}
            for r in rows]


def add_person(conn, name, email):
    """Legt eine Person an oder findet sie über die E-Mail. Gibt (id, neu?) zurück."""
    email = email.strip().lower()
    row = conn.execute("SELECT id FROM persons WHERE email = ?", (email,)).fetchone()
    if row:
        return row["id"], False
    return conn.execute("INSERT INTO persons (name, email) VALUES (?, ?)",
                        (name.strip(), email)).lastrowid, True


def update_person(conn, person_id, name, email):
    """Ändert Name/E-Mail. Bei neuer E-Mail werden auch die gespeicherten Paare umgeschrieben,
    sonst würde die Vorjahressperre die Person nicht mehr erkennen."""
    email = email.strip().lower()
    old = conn.execute("SELECT email FROM persons WHERE id = ?", (person_id,)).fetchone()
    conn.execute("UPDATE persons SET name = ?, email = ? WHERE id = ?",
                 (name.strip(), email, person_id))
    if old and old["email"] != email:
        f = _fernet()
        for r in conn.execute("SELECT id, token FROM draws").fetchall():
            pair = json.loads(f.decrypt(r["token"]))
            if old["email"] in pair:
                pair = [email if x == old["email"] else x for x in pair]
                conn.execute("UPDATE draws SET token = ? WHERE id = ?",
                             (f.encrypt(json.dumps(pair).encode()), r["id"]))


def delete_person(conn, person_id):
    conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))  # Teilnahmen + Haushalte per CASCADE


def set_memberships(conn, person_id, gids):
    """Setzt die Runden einer Person auf genau gids."""
    gids = set(gids)
    current = {r["group_id"] for r in conn.execute(
        "SELECT group_id FROM participants WHERE person_id = ?", (person_id,))}
    for gid in current - gids:
        conn.execute("DELETE FROM participants WHERE person_id = ? AND group_id = ?",
                     (person_id, gid))
    for gid in gids - current:
        conn.execute("INSERT INTO participants (group_id, person_id) VALUES (?, ?)",
                     (gid, person_id))


def list_participants(conn, gid):
    """Teilnehmer einer Runde; id = Teilnahme-ID (für Haushalte), dazu Name/E-Mail der Person."""
    return conn.execute(
        "SELECT p.id, p.group_id, p.person_id, s.name, s.email FROM participants p "
        "JOIN persons s ON s.id = p.person_id WHERE p.group_id = ? "
        "ORDER BY s.name COLLATE NOCASE", (gid,)).fetchall()


def add_members(conn, gid, person_ids):
    """Fügt Personen der Runde hinzu; gibt die Anzahl neu hinzugefügter zurück."""
    return sum(conn.execute("INSERT OR IGNORE INTO participants (group_id, person_id) "
                            "VALUES (?, ?)", (gid, pid)).rowcount for pid in person_ids)


def add_participant(conn, gid, name, email):
    """Neue (oder per E-Mail gefundene) Person direkt zur Runde hinzufügen.
    Gibt (neu angelegt?, zur Runde hinzugefügt?) zurück."""
    person_id, created = add_person(conn, name, email)
    return created, bool(add_members(conn, gid, [person_id]))


def import_persons(conn, people, gids):
    """people: Liste von (name, email). Legt neue Personen an (vorhandene E-Mails und Doppelte
    werden übersprungen) und fügt alle Zeilen den Runden gids hinzu.
    Gibt (neu, übersprungen, Runden-Zuordnungen) zurück."""
    created = assigned = 0
    for name, email in people:
        person_id, new = add_person(conn, name, email)
        created += new
        assigned += sum(add_members(conn, gid, [person_id]) for gid in gids)
    return created, len(people) - created, assigned


def delete_participant(conn, gid, pid):
    """Entfernt die Person nur aus dieser Runde – in der Personenliste bleibt sie."""
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
                        (kind, title, _norm(subject), _norm(body), 1 if active else 0)).lastrowid


def update_template(conn, tid, title, subject, body, active):
    conn.execute("UPDATE templates SET title = ?, subject = ?, body = ?, active = ? WHERE id = ?",
                 (title, _norm(subject), _norm(body), 1 if active else 0, tid))


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
