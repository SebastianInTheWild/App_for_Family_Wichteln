"""E-Mail-Versand. SMTP-Daten kommen aus den Einstellungen in der Datenbank.
Ohne SMTP-Server läuft der Dummy-Modus: Mails landen als .eml in data/outbox."""
import datetime
import smtplib
from email.message import EmailMessage

import storage

SMTP_TIMEOUT = 15


class MailError(Exception):
    pass


def render(template, **values):
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def smtp_config(conn):
    cfg = {key: storage.get_setting(conn, f"smtp_{key}") or ""
           for key in ("host", "port", "security", "user", "from")}
    token = storage.get_setting(conn, "smtp_password_enc")
    cfg["password"] = storage.decrypt_text(token) if token else ""
    cfg["port"] = int(cfg["port"] or 587)
    cfg["security"] = cfg["security"] or "starttls"
    return cfg


def save_smtp_config(conn, form):
    for key in ("host", "port", "security", "user", "from"):
        storage.set_setting(conn, f"smtp_{key}", form.get(key, "").strip())
    if form.get("password"):
        storage.set_setting(conn, "smtp_password_enc", storage.encrypt_text(form["password"]))
    if form.get("clear_password"):
        storage.set_setting(conn, "smtp_password_enc", "")


def is_dummy(conn):
    return not storage.get_setting(conn, "smtp_host")


def send_all(conn, messages):
    """messages: Liste von (to, subject, body)."""
    cfg = smtp_config(conn)
    sender = cfg["from"] or cfg["user"] or "wichteln@example.org"
    mails = []
    for to, subject, body in messages:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = sender, to, subject
        msg.set_content(body)
        mails.append(msg)

    if not cfg["host"]:
        outbox = storage.DATA_DIR / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        for msg in mails:
            (outbox / f"{stamp}_{msg['To']}.eml").write_bytes(bytes(msg))
        return

    smtp_cls = smtplib.SMTP_SSL if cfg["security"] == "ssl" else smtplib.SMTP
    try:
        # Timeout deutlich unter dem gunicorn-Timeout, damit der Fehler angezeigt wird
        with smtp_cls(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT) as smtp:
            if cfg["security"] == "starttls":
                smtp.starttls()
            if cfg["user"]:
                smtp.login(cfg["user"], cfg["password"])
            for msg in mails:
                smtp.send_message(msg)
    except (TimeoutError, smtplib.SMTPServerDisconnected) as e:
        raise MailError(f"Keine Antwort vom Mailserver {cfg['host']}:{cfg['port']} ({e}). "
                        "Passen Port und Verschlüsselung zusammen? "
                        "Üblich: 587 = STARTTLS, 465 = SSL/TLS.") from e
    except smtplib.SMTPAuthenticationError as e:
        raise MailError(f"Anmeldung am Mailserver abgelehnt – Benutzer/Passwort prüfen ({e.smtp_code}).") from e


def check_combination(cfg):
    """Warnt bei typischen Fehlkombinationen von Port und Verschlüsselung."""
    port, security = int(cfg.get("port") or 587), cfg.get("security")
    if port == 465 and security != "ssl":
        return "Port 465 erwartet normalerweise „SSL/TLS“ – mit dieser Einstellung hängt die Verbindung."
    if port in (587, 25, 2525) and security == "ssl":
        return f"Port {port} erwartet normalerweise „STARTTLS“ – mit „SSL/TLS“ hängt die Verbindung."
    return None


def send_test(conn, to):
    send_all(conn, [(to, "Wichteln: Test-E-Mail",
                     "Hallo,\n\ndiese Test-E-Mail zeigt, dass der Versand funktioniert.\n")])
