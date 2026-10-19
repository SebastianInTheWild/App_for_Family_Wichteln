"""E-Mail-Versand. SMTP-Daten kommen aus den Einstellungen in der Datenbank.
Ohne SMTP-Server läuft der Dummy-Modus: Mails landen als .eml in data/outbox."""
import datetime
import html
import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

import storage

SMTP_TIMEOUT = 15


class MailError(Exception):
    pass


def render(template, **values):
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def mail_identity(group, year):
    """(Wert für {gruppe}, Kopfzeile der Mail). Mit eigenem „Name in der Mail“ (darf {jahr}
    enthalten) steht genau dieser im Kopf, sonst „Wichteln <jahr> · <Gruppenname>“."""
    custom = (group["mail_name"] or "").strip()
    if custom:
        text = render(custom, jahr=year)
        return text, text
    return group["name"], f"Wichteln {year} · {group['name']}"


def compose(template, values, note=None, header=None):
    """Baut (Betreff, Text, HTML) aus einer Vorlage. In HTML steht {partner} fett;
    der Kopf nennt Jahr und Gruppe, damit man bei mehreren Gruppen weiß, worum es geht."""
    header = header or f"Wichteln {values['jahr']} · {values['gruppe']}"
    subject = render(template["subject"], **values)
    text = f"🎁 {header}\n\n" + (f"{note}\n\n" if note else "") + render(template["body"], **values)
    return subject, text, render_html(template["body"], values, header, note)


def render_html(body, values, header, note=None):
    out = html.escape(body)
    for key, value in values.items():
        value = html.escape(str(value))
        if key == "partner":
            value = f'<strong style="color:#b3261e;font-size:1.1em">{value}</strong>'
        out = out.replace("{" + key + "}", value)
    out = re.sub(r"(?m)^( +)", lambda m: "&nbsp;" * len(m.group(1)), out).replace("\n", "<br>\n")
    note_html = (f'<p style="margin:0 0 16px;padding:8px 12px;background:#fff6d6;border-radius:6px;'
                 f'font-size:14px">{html.escape(note)}</p>') if note else ""
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px 12px;background:#faf7f2">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:560px;background:#ffffff;border:1px solid #e3ddd3;border-radius:12px;overflow:hidden">
  <tr><td style="background:#b3261e;color:#ffffff;padding:16px 24px;font:bold 18px Arial,sans-serif">🎁 {html.escape(header)}</td></tr>
  <tr><td style="padding:24px;color:#2b2b2b;font:16px/1.6 Arial,sans-serif">{note_html}{out}</td></tr>
</table>
</td></tr></table>
</body></html>
"""


def smtp_config(conn):
    cfg = {key: storage.get_setting(conn, f"smtp_{key}") or ""
           for key in ("host", "port", "security", "user", "from", "from_name")}
    token = storage.get_setting(conn, "smtp_password_enc")
    cfg["password"] = storage.decrypt_text(token) if token else ""
    cfg["port"] = int(cfg["port"] or 587)
    cfg["security"] = cfg["security"] or "starttls"
    return cfg


def save_smtp_config(conn, form):
    for key in ("host", "port", "security", "user", "from", "from_name"):
        storage.set_setting(conn, f"smtp_{key}", form.get(key, "").strip())
    if form.get("password"):
        storage.set_setting(conn, "smtp_password_enc", storage.encrypt_text(form["password"]))
    if form.get("clear_password"):
        storage.set_setting(conn, "smtp_password_enc", "")


def sender_header(cfg):
    """From-Kopfzeile: „Absendername <adresse>“. Ein Name im Adressfeld zählt nur ohne eigenes Namensfeld."""
    name, address = parseaddr(cfg["from"])
    address = address or (cfg["user"] if "@" in cfg["user"] else "") or "wichteln@example.org"
    return formataddr((cfg.get("from_name") or name, address))


def is_dummy(conn):
    return not storage.get_setting(conn, "smtp_host")


def send_all(conn, messages):
    """messages: Liste von (to, subject, text, html)."""
    cfg = smtp_config(conn)
    sender = sender_header(cfg)
    mails = []
    for to, subject, text, html_body in messages:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = sender, to, subject
        msg.set_content(text)
        msg.add_alternative(html_body, subtype="html")
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

