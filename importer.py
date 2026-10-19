"""Teilnehmer-Import aus CSV/TXT oder eingefügtem Text.
Je Zeile eine Person, z. B. „Anna;anna@x.de“, „Anna, anna@x.de“, „Anna <anna@x.de>“,
„anna@x.de“ (Name aus der Adresse) – Kopfzeilen und Leerzeilen werden ignoriert."""
import re

EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def decode(data):
    """Excel speichert CSV oft als UTF-8 mit BOM oder Windows-1252."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def parse(text):
    """Gibt ([(name, email)], [ungültige Zeilen]) zurück."""
    people, invalid = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = EMAIL.search(line)
        if not match:
            if not re.search(r"(?i)e-?mail|adresse", line):  # Kopfzeile still überspringen
                invalid.append(line[:40])
            continue
        email = match.group(0).lower()
        name = (line[:match.start()] + " " + line[match.end():])
        name = re.sub(r"[;,\t<>\"'|()]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            name = " ".join(p.capitalize() for p in re.split(r"[._-]+", email.split("@")[0]) if p)
        people.append((name, email))
    return people, invalid
