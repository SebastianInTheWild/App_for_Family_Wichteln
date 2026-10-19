"""E-Mail-Versand. SMTP-Daten kommen aus den Einstellungen in der Datenbank.
Ohne SMTP-Server läuft der Dummy-Modus: Mails landen als .eml in data/outbox."""
import datetime
import smtplib
from email.message import EmailMessage

import storage


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
    with smtp_cls(cfg["host"], cfg["port"], timeout=30) as smtp:
        if cfg["security"] == "starttls":
            smtp.starttls()
        if cfg["user"]:
            smtp.login(cfg["user"], cfg["password"])
        for msg in mails:
            smtp.send_message(msg)


def send_test(conn, to):
    send_all(conn, [(to, "Wichteln: Test-E-Mail",
                     "Hallo,\n\ndiese Test-E-Mail zeigt, dass der Versand funktioniert.\n")])
