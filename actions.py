"""Auslosen und Versenden – genutzt von der Web-Oberfläche und vom Zeitplan."""
import datetime
import random
import threading

import mailer
import storage
from matching import NoMatchingPossible, draw

KIND_TITLES = {"mail": "Zuteilung", "reminder": "Erinnerung"}
_rng = random.SystemRandom()


class ActionError(Exception):
    pass


# Web-Threads und Zeitplan dürfen nicht gleichzeitig auslosen (z. B. Doppelklick)
_draw_lock = threading.Lock()


def compute_draw(conn, gid, year):
    people = storage.list_participants(conn, gid)
    by_id = {p["id"]: p for p in people}
    emails = [p["email"] for p in people]

    same_household = set()
    for a, b in storage.household_pairs(conn, gid):
        same_household |= {(by_id[a]["email"], by_id[b]["email"]),
                           (by_id[b]["email"], by_id[a]["email"])}

    lookback = storage.get_group(conn, gid)["lookback_years"]
    previous = storage.load_draws(conn, gid, range(year - lookback, year))

    try:
        return draw(emails, lambda g, r: (g, r) in same_household or (g, r) in previous)
    except NoMatchingPossible as e:
        raise ActionError(str(e)) from e


def perform_draw(conn, gid, year):
    """Lost aus, speichert verschlüsselt und verschickt die Zuteilungs-Mails."""
    if not _draw_lock.acquire(blocking=False):
        raise ActionError("Es läuft gerade schon eine Auslosung – bitte kurz warten.")
    try:
        return _perform_draw(conn, gid, year)
    finally:
        _draw_lock.release()


def _perform_draw(conn, gid, year):
    if any(r["year"] == year for r in storage.draw_overview(conn, gid)):
        raise ActionError(f"Für {year} gibt es bereits eine Auslosung. Erst löschen, dann neu auslosen.")
    _require_templates(conn, "mail")
    result = compute_draw(conn, gid, year)
    storage.save_draw(conn, gid, year, result.items())
    conn.commit()  # Auslosung bleibt erhalten, auch wenn der Versand scheitert
    try:
        sent = send_for_year(conn, gid, year, "mail")
    except Exception as e:  # noqa: BLE001
        raise ActionError(f"Auslosung {year} gespeichert, aber der Versand ist fehlgeschlagen: {e} "
                          "– über „Erneut senden“ nachholen.") from e
    return f"Auslosung {year} gespeichert, {sent}."


def _require_templates(conn, kind):
    templates = storage.active_templates(conn, kind)
    if not templates:
        raise ActionError(f"Keine aktive Vorlage für „{KIND_TITLES[kind]}“ – "
                          "bitte unter E-Mail-Vorlagen eine einschalten.")
    return templates


def send_for_year(conn, gid, year, kind):
    """kind: 'mail' (Zuteilung) oder 'reminder' (Erinnerung). Jede Person bekommt
    eine zufällig gewählte aktive Vorlage."""
    pairs = storage.load_draws(conn, gid, [year])
    if not pairs:
        raise ActionError(f"Für {year} gibt es noch keine Auslosung.")
    templates = _require_templates(conn, kind)
    gruppe, header = mailer.mail_identity(storage.get_group(conn, gid), year)
    names = {p["email"]: p["name"] for p in storage.list_participants(conn, gid)}

    messages, skipped = [], 0
    for giver, receiver in sorted(pairs):
        if giver not in names or receiver not in names:
            skipped += 1  # Teilnehmer wurde inzwischen gelöscht
            continue
        values = {"name": names[giver], "partner": names[receiver], "jahr": year,
                  "gruppe": gruppe}
        messages.append((giver, *mailer.compose(_rng.choice(templates), values, header=header)))

    mailer.send_all(conn, messages)
    where = "in data/outbox abgelegt (Dummy-Modus)" if mailer.is_dummy(conn) else "versendet"
    note = f", {skipped} übersprungen (Teilnehmer gelöscht)" if skipped else ""
    return f"{len(messages)} E-Mails {where}{note}"


def send_test(conn, to, gid, template_id=None):
    """Schickt eine Beispiel-Mail, die genauso aussieht wie die echte Wichtel-Mail.
    Ohne template_id wird – wie beim echten Versand – eine Zuteilungs-Vorlage zufällig gewählt."""
    if template_id:
        template = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
        if template is None:
            raise ActionError("Vorlage nicht gefunden.")
    else:
        template = _rng.choice(_require_templates(conn, "mail"))
    year = datetime.date.today().year
    gruppe, header = mailer.mail_identity(storage.get_group(conn, gid), year)
    values = {"name": "Test-Wichtel", "partner": "Erika Musterfrau", "jahr": year, "gruppe": gruppe}
    subject, text, html_body = mailer.compose(
        template, values, header=header,
        note=f"Test-E-Mail: So sieht die Vorlage „{template['title']}“ aus. "
             "Name und Partner sind Beispielwerte.")
    mailer.send_all(conn, [(to, f"[Test] {subject}", text, html_body)])
    return template["title"]
