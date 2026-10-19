"""Hintergrund-Thread, der fällige Jobs (Auslosung, Erinnerung) ausführt."""
import datetime
import logging
import os
import threading
import time
from zoneinfo import ZoneInfo

import actions
import rules
import storage

TZ = ZoneInfo(os.environ.get("TZ") or "Europe/Berlin")
INTERVAL_SECONDS = 30
log = logging.getLogger("wichteln.scheduler")


def now_local():
    return datetime.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")


def materialize_rules(conn, now):
    """Erzeugt für jede Jahresregel den Job des aktuellen Jahres (falls noch nicht vorhanden)."""
    year = int(now[:4])
    for rule in storage.list_rules(conn):
        day = rules.occurrence(rule, year)
        if day is None:
            continue
        run_at = f"{day.isoformat()}T{rule['time']}"
        if run_at >= rule["created_at"]:  # Termine vor Anlage der Regel nicht nachholen
            storage.add_rule_job(conn, rule["id"], rule["kind"], year, run_at)


def run_due_jobs():
    now = now_local()
    with storage.connect() as conn:
        materialize_rules(conn, now)
        due = storage.claim_due_jobs(conn, now)
    for job in due:
        try:
            with storage.connect() as conn:
                if job["kind"] == "draw":
                    message = actions.perform_draw(conn, job["year"])
                else:
                    message = "Erinnerung: " + actions.send_for_year(conn, job["year"], "reminder")
            status = "done"
        except Exception as e:  # noqa: BLE001 – Fehler am Job anzeigen
            status, message = "error", str(e)
        with storage.connect() as conn:
            storage.finish_job(conn, job["id"], status, message)
        log.info("Job %s (%s %s): %s – %s", job["id"], job["kind"], job["year"], status, message)


def _loop():
    while True:
        try:
            run_due_jobs()
        except Exception:  # noqa: BLE001 – Thread darf nie sterben
            log.exception("Zeitplan-Durchlauf fehlgeschlagen")
        time.sleep(INTERVAL_SECONDS)


def start():
    threading.Thread(target=_loop, name="wichtel-scheduler", daemon=True).start()
