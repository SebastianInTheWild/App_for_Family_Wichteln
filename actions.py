"""Auslosen und Versenden – genutzt von der Web-Oberfläche und vom Zeitplan."""
import mailer
import storage
from matching import NoMatchingPossible, draw


class ActionError(Exception):
    pass


def compute_draw(conn, year):
    people = storage.list_participants(conn)
    by_id = {p["id"]: p for p in people}
    emails = [p["email"] for p in people]

    same_household = set()
    for a, b in storage.household_pairs(conn):
        same_household |= {(by_id[a]["email"], by_id[b]["email"]),
                           (by_id[b]["email"], by_id[a]["email"])}

    lookback = int(storage.get_setting(conn, "lookback_years") or 0)
    previous = storage.load_draws(conn, range(year - lookback, year))

    try:
        return draw(emails, lambda g, r: (g, r) in same_household or (g, r) in previous)
    except NoMatchingPossible as e:
        raise ActionError(str(e)) from e


def perform_draw(conn, year):
    """Lost aus, speichert verschlüsselt und verschickt die Zuteilungs-Mails."""
    if any(r["year"] == year for r in storage.draw_overview(conn)):
        raise ActionError(f"Für {year} gibt es bereits eine Auslosung. Erst löschen, dann neu auslosen.")
    result = compute_draw(conn, year)
    storage.save_draw(conn, year, result.items())
    conn.commit()  # Auslosung bleibt erhalten, auch wenn der Versand scheitert
    try:
        sent = send_for_year(conn, year, "mail")
    except Exception as e:  # noqa: BLE001
        raise ActionError(f"Auslosung {year} gespeichert, aber der Versand ist fehlgeschlagen: {e} "
                          "– über „Erneut senden“ nachholen.") from e
    return f"Auslosung {year} gespeichert, {sent}."


def send_for_year(conn, year, template):
    """template: 'mail' (Zuteilung) oder 'reminder' (Erinnerung)."""
    pairs = storage.load_draws(conn, [year])
    if not pairs:
        raise ActionError(f"Für {year} gibt es noch keine Auslosung.")
    names = {p["email"]: p["name"] for p in storage.list_participants(conn)}
    subject = storage.get_setting(conn, f"{template}_subject")
    body = storage.get_setting(conn, f"{template}_body")

    messages, skipped = [], 0
    for giver, receiver in sorted(pairs):
        if giver not in names or receiver not in names:
            skipped += 1  # Teilnehmer wurde inzwischen gelöscht
            continue
        values = {"name": names[giver], "partner": names[receiver], "jahr": year}
        messages.append((giver, mailer.render(subject, **values), mailer.render(body, **values)))

    mailer.send_all(conn, messages)
    where = "in data/outbox abgelegt (Dummy-Modus)" if mailer.is_dummy(conn) else "versendet"
    note = f", {skipped} übersprungen (Teilnehmer gelöscht)" if skipped else ""
    return f"{len(messages)} E-Mails {where}{note}"
