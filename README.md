# Wichteln – Entwurf

Kleine Web-App für die jährliche Wichtel-Auslosung.

- **Teilnehmer** mit Name und E-Mail pflegen
- **Haushalts-Matrix**: Wer zusammen wohnt, zieht sich nicht
- **E-Mail-Vorlagen** für Zuteilung und Erinnerung, Platzhalter `{name}`, `{partner}`, `{jahr}`
- **Auslosung**: Testlauf oder echte Auslosung + E-Mail an jeden; Zuteilung erneut senden, Erinnerung sofort senden
- **Zeitplan**: Auslosung/Versand und Erinnerungen zu festen Zeitpunkten automatisch ausführen
- **Einstellungen**: SMTP-Server in der Web-App eintragen, Test-E-Mail senden
- Paare werden **verschlüsselt** (Fernet/AES) in SQLite gespeichert und
  in den Folgejahren gesperrt (Zeitraum einstellbar, Standard: 1 Jahr)

## Lokal starten

```powershell
pip install -r requirements.txt
python app.py      # http://localhost:8080
```

## Auf dem Server (Portainer)

1. Stacks → Add stack → **Repository**
   - URL: `https://github.com/SebastianInTheWild/App_for_Family_Wichteln`
   - Reference: `refs/heads/main`, Compose path: `docker-compose.yml`
2. Optional `ADMIN_PASSWORD` setzen (Browser-Login), deployen.
3. Aufruf: `http://<server>:8090`

Portainer baut das Image aus dem `Dockerfile` direkt auf dem Server.
Daten (Datenbank, Schlüssel, Dummy-Outbox) liegen auf dem Host in
`/home/sebastian/docker/wichteln/data` – Pfad bei Bedarf in `docker-compose.yml` anpassen.
Updates: pushen, dann im Stack „Pull and redeploy“.

## Konfiguration

SMTP-Server, Vorlagen und Zeitplan werden in der Web-App gepflegt. Per Umgebungsvariable:

| Variable | Zweck |
|---|---|
| `ADMIN_PASSWORD` | Schützt die Seite per Browser-Login (Benutzername beliebig). Ohne: kein Schutz! |
| `FLASK_SECRET` | Fester Session-Schlüssel |
| `WICHTEL_KEY` | Fernet-Schlüssel für Paare und SMTP-Passwort. Ohne: wird in `data/secret.key` erzeugt |
| `TZ` | Zeitzone für den Zeitplan (Standard `Europe/Berlin`) |
| `WICHTEL_SCHEDULER` | `0` schaltet den Zeitplan-Thread ab |

Solange kein SMTP-Server eingetragen ist, läuft der **Dummy-Modus**: Mails landen
als `.eml` in `data/outbox`.

**Wichtig:** `data/secret.key` (bzw. `WICHTEL_KEY`) sichern. Ohne den Schlüssel
lassen sich Vorjahrespaare und SMTP-Passwort nicht mehr lesen.

## Zeitplan

- **Jährliche Termine** (Regeln): z. B. „1. Sonntag im November, 10:00“,
  „1. Dezember“, „3. Advent“ oder „letzter Freitag im November“. Daraus wird jedes
  Jahr automatisch ein Termin für das laufende Jahr erzeugt.
  - Liegt der Termin dieses Jahres beim Anlegen schon in der Vergangenheit, startet die Regel erst nächstes Jahr.
  - „Aussetzen“ überspringt einen Termin nur für dieses Jahr; die Regel bleibt.
- **Einmalige Termine** mit festem Datum und Jahr.
- Ein Hintergrund-Thread prüft alle 30 Sekunden auf fällige Termine.
- „Auslosen & Zuteilung senden“ lost aus, speichert und verschickt – wie der Button auf der Auslosungs-Seite.
- „Erinnerung senden“ braucht eine bestehende Auslosung für das Jahr.
- War der Server zum Termin aus, wird der Termin beim nächsten Start nachgeholt.
- Ergebnis oder Fehlermeldung steht am Termin in der Liste.

## Hinweise zum Entwurf

- Die Verschlüsselung schützt die Paare vor einem Blick in die Datenbankdatei.
  Wer Server-Zugriff hat (DB + Schlüssel), kann sie entschlüsseln – das ist
  nötig, damit die App die Vorjahressperre prüfen und Erinnerungen schicken kann.
- Die Auslosung wird vor dem Versand gespeichert. Scheitert der Versand,
  lässt er sich über „Erneut senden“ nachholen, ohne neu auszulosen.
- Im Dummy-Modus stehen die Paare im Klartext in `data/outbox` – nur zum Testen.
- Noch kein CSRF-Schutz; die Seite ist nur für den Organisator gedacht.
