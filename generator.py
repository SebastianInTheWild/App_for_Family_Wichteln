"""Würfelt neue lustige Vorlagen aus Bausteinen zusammen – getrennt für Zuteilung und Erinnerung.
Platzhalter ({name}, {partner}, {jahr}) bleiben erhalten und werden erst beim Versand gefüllt."""
import random

_rng = random.SystemRandom()

PERSONAS = [
    {"title": "Elf Kevin", "greet": "Hey {name}!",
     "sign": "Elf Kevin 🧝\n(Paketabteilung, drittes Regal links)"},
    {"title": "Der Weihnachtsmann persönlich", "greet": "Ho ho ho, liebe/r {name}!",
     "sign": "Dein Weihnachtsmann 🎅\n(diktiert, aber wegen Rentierfütterung nicht unterschrieben)"},
    {"title": "Plätzchen-Polizei", "greet": "Allgemeine Verkehrskontrolle, {name}!",
     "sign": "Wachtmeisterin Zimtstern 👮\nPlätzchen-Polizei, Revier Nordpol"},
    {"title": "Pressestelle des Christkinds", "greet": "Sehr geehrte/r {name},",
     "sign": "Mit himmlischen Grüßen\nPressestelle des Christkinds 👼"},
    {"title": "Lebkuchen-Gewerkschaft", "greet": "Liebes Gewerkschaftsmitglied {name},",
     "sign": "Solidarische Grüße\nVereinigte Lebkuchen-Gewerkschaft (VLG) 🍪"},
    {"title": "Schneemann Herbert", "greet": "Na, {name}?",
     "sign": "Schneemann Herbert ☃️\n(schmilzt leider gerade ein bisschen)"},
    {"title": "Rentier-Flugsicherung", "greet": "Flugsicherung an {name}, bitte kommen!",
     "sign": "Rentier-Flugsicherung Nordpol 🦌\nTower, Frequenz 24.12"},
]

MAIL = {
    "subjects": [
        "🎁 Wichteln {jahr}: Das Los ist gefallen, {name}!",
        "🤫 Top secret, {name}: Dein Wichtelauftrag {jahr}",
        "✨ Es ist entschieden! Wichteln {jahr}",
        "📦 Lieferung vom Nordpol für {name}",
        "🎄 Achtung, {name}: Du hast gezogen!",
    ],
    "intros": [
        "nach langen Beratungen, einer Schneeballschlacht und zwei Tassen Kakao ist die Entscheidung gefallen.",
        "die Lostrommel hat sich gedreht. Dreimal. Einmal davon versehentlich mit einem Rentier drin.",
        "unser hochmoderner Wichtel-Computer (ein Hamster in einem Laufrad) hat gerechnet.",
        "wir haben die Namen in einen Weihnachtsstiefel geworfen, kräftig geschüttelt und blind gezogen.",
        "die Sterne standen günstig, der Glühwein war warm und das Los ist gezogen.",
    ],
    "reveals": [
        "Du beschenkst dieses Jahr: 🎁 {partner} 🎁",
        "Dein Wichtelkind {jahr} heißt: {partner}",
        "Das Los ist gefallen auf: ✨ {partner} ✨",
        "Trommelwirbel … 🥁 … {partner}!",
    ],
    "tips": [
        "Verrate es niemandem. Nicht mal der Kaffeemaschine.",
        "Unauffällig beobachten, was {partner} sich wünschen könnte. Unauffällig heißt: kein Fernglas.",
        "Ein gutes Geschenk sagt „Ich habe an dich gedacht“, nicht „Lag noch im Keller“.",
        "Geschenkpapier ist kein Luxus, sondern Pflicht. Zeitungspapier zählt als Notlösung.",
        "Bei Ratlosigkeit gilt: Schokolade geht immer. Fast immer. Meistens.",
        "Pokerface üben – spätestens beim Auspacken guckt dich {partner} prüfend an.",
        "Gutscheine sind erlaubt, solange sie nicht „1x Spülmaschine ausräumen“ lauten.",
        "Socken nur, wenn sie wirklich, wirklich lustig sind.",
    ],
    "closings": [
        "Diese Nachricht zerstört sich nicht selbst. Bitte trotzdem nicht rumzeigen.",
        "Wir zählen auf dich – und die Rentiere auch.",
        "Möge dein Geschenkpapier nie reißen und dein Klebeband nie verschwinden.",
        "Und denk dran: Vorfreude ist die schönste Freude. Direkt nach Plätzchen.",
    ],
}

REMINDER = {
    "subjects": [
        "⏰ Kleine Erinnerung, {name}: Wichteln {jahr}!",
        "🦌 Die Rentiere fragen nach, {name} …",
        "🎄 Countdown läuft: Hast du schon was für dein Wichtelkind?",
        "📋 Statusabfrage Wichteln {jahr}",
        "🔔 Bimmel bimmel, {name}: Geschenk-Check!",
    ],
    "intros": [
        "wir wollten nur mal ganz unverbindlich und völlig ohne Druck nachfragen. (Ein bisschen Druck.)",
        "die Tage werden kürzer, die Plätzchendosen leerer – und die Wichtelzeit rückt näher.",
        "unser Hamster-Computer meldet: Der Wichteltag kommt näher. Er rennt schon schneller.",
        "beim letzten Kontrollflug über deine Straße haben wir keine verdächtigen Einkaufstüten gesehen.",
        "nur damit es nicht untergeht zwischen Adventskalender und Glühweinstand:",
    ],
    "status": [
        "Dein Wichtelkind: {partner}\nGeschenk-Status: ❓ unbekannt",
        "Zur Erinnerung, falls die erste Mail im Spam gelandet ist: Du beschenkst {partner}.",
        "Wichtelkind {jahr}: {partner}\nVorbereitung: ⏳ wird hoffentlich gerade erledigt",
        "Akte {partner}: Geschenk noch nicht gemeldet.",
    ],
    "tips": [
        "Heute Ideen sammeln, morgen kaufen, übermorgen einpacken – ein todsicherer Plan.",
        "„Ich hol morgen was“ ist seit Jahrhunderten die häufigste Ausrede im Dezember.",
        "Online bestellen geht schnell – aber Lieferzeiten im Dezember sind wie Rentiere: unberechenbar.",
        "Schon eingepackt? Dann gönn dir ein Plätzchen. Du hast es dir verdient.",
        "Keine Idee? Frag unauffällig jemanden, der {partner} gut kennt. Aber wirklich unauffällig.",
        "Selbstgemachtes zählt doppelt. Selbstgemachtes aus der Mikrowelle zählt einfach.",
    ],
    "closings": [
        "Falls du schon fertig bist: Ignoriere diese Mail und fühl dich großartig.",
        "Wir glauben an dich. Die Rentiere sind noch unentschlossen.",
        "Kopf hoch – bis zum Wichteltag ist noch Zeit. Ein bisschen.",
        "Bis bald unterm Weihnachtsbaum!",
    ],
}


def generate(kind):
    """Gibt {title, subject, body} zurück; kind = 'mail' oder 'reminder'."""
    blocks = MAIL if kind == "mail" else REMINDER
    persona = _rng.choice(PERSONAS)
    middle = _rng.choice(blocks["reveals"] if kind == "mail" else blocks["status"])
    tips = "\n".join(f"  • {t}" for t in _rng.sample(blocks["tips"], 3))
    intro = _rng.choice(blocks["intros"])
    if persona["greet"].endswith(("!", "?")):  # nach „Hallo …,“ klein weiter, nach „!“ groß
        intro = intro[0].upper() + intro[1:]
    body = (f"{persona['greet']}\n\n"
            f"{intro}\n\n"
            f"{middle}\n\n"
            f"{'Ein paar Tipps für deine Mission:' if kind == 'mail' else 'Kleine Hilfe vom Nordpol:'}\n"
            f"{tips}\n\n"
            f"{_rng.choice(blocks['closings'])}\n\n"
            f"{persona['sign']}\n")
    return {"title": f"{persona['title']} (generiert)",
            "subject": _rng.choice(blocks["subjects"]), "body": body}
