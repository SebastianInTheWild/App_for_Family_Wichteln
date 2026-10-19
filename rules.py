"""Jährlich wiederkehrende Termine: Datum eines Jahres berechnen und Regel beschreiben."""
import calendar
import datetime

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]
NTH = {1: "1.", 2: "2.", 3: "3.", 4: "4.", -1: "letzter"}
MODES = ("nth_weekday", "fixed_date", "advent")


def occurrence(rule, year):
    """Datum der Regel im angegebenen Jahr oder None, falls es keins gibt."""
    mode, month = rule["mode"], rule["month"]
    if mode == "fixed_date":
        last = calendar.monthrange(year, month)[1]
        return datetime.date(year, month, min(rule["day"], last))
    if mode == "nth_weekday":
        nth, weekday = rule["nth"], rule["weekday"]
        if nth == -1:
            d = datetime.date(year, month, calendar.monthrange(year, month)[1])
            return d - datetime.timedelta(days=(d.weekday() - weekday) % 7)
        first = datetime.date(year, month, 1)
        d = first + datetime.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (nth - 1))
        return d if d.month == month else None
    if mode == "advent":
        christmas_eve = datetime.date(year, 12, 24)
        fourth = christmas_eve - datetime.timedelta(days=(christmas_eve.weekday() - 6) % 7)
        return fourth - datetime.timedelta(weeks=4 - rule["nth"])
    raise ValueError(mode)


def describe(rule):
    if rule["mode"] == "fixed_date":
        text = f"{rule['day']}. {MONTHS[rule['month'] - 1]}"
    elif rule["mode"] == "nth_weekday":
        text = f"{NTH[rule['nth']]} {WEEKDAYS[rule['weekday']]} im {MONTHS[rule['month'] - 1]}"
    else:
        text = f"{rule['nth']}. Advent"
    return f"{text}, {rule['time']} Uhr"


def next_occurrence(rule, now):
    """Nächster Termin ab now ('YYYY-MM-DDTHH:MM') als String oder None."""
    year = int(now[:4])
    for y in (year, year + 1, year + 2):
        d = occurrence(rule, y)
        if d and f"{d.isoformat()}T{rule['time']}" >= now:
            return f"{d.isoformat()}T{rule['time']}"
    return None
