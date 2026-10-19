"""Mitgelieferte Vorlagen. Werden beim ersten Start in die Datenbank übernommen
und lassen sich danach in der Web-App bearbeiten, abschalten oder löschen.
Platzhalter: {name} (Schenker), {partner} (Beschenkter, in HTML-Mails fett), {jahr}."""

MAIL = [
    {
        "title": "Nordpol-Zentrale",
        "subject": "🎅 Streng geheim: Dein Wichtel-Auftrag {jahr}",
        "body": """Ho ho ho, {name}!

Hier spricht die Wichtel-Zentrale vom Nordpol. Nach stundenlangen Beratungen,
drei Kannen Glühwein und einem knappen Votum der Rentiere steht fest:

Du beschenkst dieses Jahr: 🎁 {partner} 🎁

Deine Mission, solltest du sie annehmen (du musst):
  1. Erzähl es NIEMANDEM. Auch nicht dem Hund. Der Hund petzt.
  2. Finde ein Geschenk, bei dem {partner} „Oh, wie aufmerksam!“ sagt –
     und nicht „Oh … Socken.“
  3. Pack es so ein, dass man nicht sofort sieht, dass es Socken sind.

Diese E-Mail zerstört sich nicht selbst. Das musst du schon selbst machen.

Weihnachtliche Grüße
Die Wichtel-Zentrale 🦌
(Abteilung Geheimhaltung & Geschenkpapier)
""",
    },
    {
        "title": "Geheimagent",
        "subject": "🕶️ Mission {jahr}: Zielperson zugewiesen",
        "body": """Agent {name},

diese Nachricht ist nur für deine Augen bestimmt. Falls du nicht {name} bist:
Bitte sofort weglegen und so tun, als wärst du nie hier gewesen.

Nach monatelanger Überwachung (wir haben in eure Plätzchendose geschaut)
hat das Hauptquartier deine Zielperson festgelegt:

🎯 {partner}

Dein Auftrag:
  • Unauffällig herausfinden, was sich {partner} wünscht.
    „Na, was wünschst du dir denn so – rein hypothetisch?“ ist zu auffällig.
    Wir haben es getestet.
  • Geschenk beschaffen, ohne Spuren zu hinterlassen.
  • Übergabe am Wichteltag mit Pokerface.

Sollte deine Tarnung auffliegen, wird das Hauptquartier jede Kenntnis
von dir abstreiten.

Viel Erfolg, Agent.
H. Q. (Hauptquartier für Quatsch)
""",
    },
    {
        "title": "Amt für Wichtelangelegenheiten",
        "subject": "Bescheid Nr. W-{jahr}/007 über Ihre Wichtelzuteilung",
        "body": """Sehr geehrte/r {name},

nach Prüfung Ihrer Unterlagen gemäß § 24 Abs. 12 der Wichtelordnung (WichtO)
ergeht folgender

B E S C H E I D

1. Ihnen wird für das Wichteljahr {jahr} folgende beschenkungsberechtigte
   Person zugewiesen: {partner}
2. Die Zuteilung ist streng vertraulich. Verstöße gegen die Schweigepflicht
   werden mit Plätzchenentzug geahndet.
3. Das Geschenk ist fristgerecht, ordnungsgemäß verpackt und mit mindestens
   einer Schleife einzureichen.
4. Socken gelten nur in begründeten Ausnahmefällen als Geschenk
   (Antrag über Formular W-17b).

Rechtsbehelfsbelehrung: Gegen diesen Bescheid kann innerhalb von 0 Tagen
Widerspruch eingelegt werden. Der Widerspruch wird ignoriert.

Mit festlichen Grüßen
Im Auftrag
Ruprecht Knecht
Amt für Wichtelangelegenheiten, Referat Geschenke & Geheimnisse
""",
    },
    {
        "title": "Eilmeldung",
        "subject": "📺 EILMELDUNG: Wichtel-Los {jahr} gezogen!",
        "body": """+++ EILMELDUNG +++ EILMELDUNG +++

Guten Abend, {name}, und willkommen zu den Wichtel-Nachrichten.

Wie der Nordpol soeben bestätigte, ist die Auslosung für das Wichteljahr
{jahr} abgeschlossen. Unserem Reporter vor Ort, einem leicht unterkühlten
Rentier, liegen exklusive Informationen vor. Du beschenkst in diesem Jahr:

📣 {partner} 📣

Experten zeigen sich überrascht, aber zuversichtlich. „Das wird ein tolles
Geschenk“, so ein Sprecher des Nordpols, „sofern es nicht wieder ein
Duftkerzen-Set wird.“

Und nun zum Wetter: Es bleibt geheimnisvoll, mit vereinzelten Schauern
von Vorfreude. Gegen Ende des Monats ist mit erhöhtem
Geschenkpapieraufkommen zu rechnen.

Das war's aus dem Studio. Und denk dran: Das bleibt unter uns.
""",
    },
]

REMINDER = [
    {
        "title": "Nordpol-Kontrollanruf",
        "subject": "⏰ Psst, {name} … der Wichtel-Countdown läuft!",
        "body": """Hallo {name},

die Wichtel-Zentrale hat einen Kontrollanruf gemacht und möchte höflich
nachfragen: Hast du schon ein Geschenk für {partner}? 🤔

Falls ja: Bravo! Du bist offiziell Wichtel des Monats. 🏅
Falls nein: Keine Panik. Noch ist Zeit. Ein bisschen. Nicht viel.
Die Rentiere werden langsam nervös.

Kleiner Tipp aus der Erfahrung des Nordpols:
„Ich hol morgen was“ ist seit 1847 die häufigste Lüge im Dezember.

Wir glauben an dich!
Die Wichtel-Zentrale 🎄

PS: Du weißt nicht mehr, wen du beschenkst? Na, {partner}!
Gut, dass wir nachgefragt haben.
""",
    },
    {
        "title": "Funkspruch",
        "subject": "📡 Funkspruch an Agent {name}: Statusbericht angefordert",
        "body": """*knister* … Agent {name}, bitte kommen … *knister*

Das Hauptquartier fordert einen Statusbericht zur Mission {jahr}.

Zielperson: {partner}
Status Geschenk: UNBEKANNT ⚠️

Unsere Satelliten konnten bisher keine verdächtigen Einkaufstüten in deiner
Nähe ausmachen. Das ist entweder ein Zeichen exzellenter Tarnung – oder du
hast es vergessen. Wir gehen von Ersterem aus. Optimistisch.

Zur Erinnerung: Ein Agent erscheint niemals mit leeren Händen. Und niemals
mit einer an der Tankstelle gekauften Pralinenschachtel. (Wir sehen alles.)

Over and out.
H. Q. *knister*
""",
    },
    {
        "title": "Amtliche Erinnerung",
        "subject": "Freundliche Erinnerung zu Vorgang W-{jahr}/007",
        "body": """Sehr geehrte/r {name},

bei der Durchsicht unserer Akten ist uns aufgefallen, dass zum Vorgang
„Beschenkung von {partner}“ bisher kein Geschenkeingang verzeichnet ist.

Sicherlich handelt es sich um ein Versehen, oder das Geschenk liegt bereits
gut versteckt im Kleiderschrank. In diesem Fall betrachten Sie dieses
Schreiben bitte als gegenstandslos und sich selbst als vorbildlich.

Andernfalls bitten wir, das Geschenk bis zum Wichteltag zu beschaffen.
Bei Fristversäumnis wird eine Mahngebühr in Höhe von einem selbstgebackenen
Plätzchen fällig.

Mit festlichen Grüßen
Im Auftrag
Ruprecht Knecht
Amt für Wichtelangelegenheiten
""",
    },
    {
        "title": "Rudolph",
        "subject": "🦌 Rudolph hier. Wir müssen reden, {name}.",
        "body": """Hallo {name},

hier ist Rudolph. Ja, DER Rudolph. Meine Nase leuchtet gerade besonders hell,
weil ich mir Sorgen mache.

Ich habe gehört, dass du dieses Jahr {partner} beschenkst. Schöne Sache!
Und ich habe auch gehört … dass da noch nichts besorgt ist?

Ich will nicht drängeln. Aber wir Rentiere planen unsere Route schon seit
August. Mit Excel. Und Farben.

Kleiner Vorschlag von Rentier zu Mensch:
  🛒 Heute: Ideen sammeln
  🎁 Morgen: kaufen
  🎀 Übermorgen: einpacken (mit Schleife, bitte!)

Ich glaub an dich. Die anderen Rentiere sind skeptisch,
aber Comet ist ja immer skeptisch.

Rentierliche Grüße
Rudolph 🔴
""",
    },
]

DEFAULTS = {"mail": MAIL, "reminder": REMINDER}
