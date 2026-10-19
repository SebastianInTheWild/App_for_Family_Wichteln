"""Wichtel-App: Teilnehmer, Haushalts-Matrix, E-Mail-Vorlagen, Auslosung, Zeitplan, Einstellungen."""
import datetime
import hmac
import os
import sqlite3

from flask import Flask, Response, flash, redirect, render_template, request, url_for

import mailer
import rules
import scheduler
import storage
from actions import ActionError, compute_draw, perform_draw, send_for_year

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET") or os.urandom(24)
storage.init_db()
if os.environ.get("WICHTEL_SCHEDULER", "1") != "0":
    scheduler.start()


@app.before_request
def require_login():
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", password):
        return None
    return Response("Login erforderlich", 401, {"WWW-Authenticate": 'Basic realm="Wichteln"'})


@app.context_processor
def inject_globals():
    with storage.connect() as conn:
        return {"dummy_mail": mailer.is_dummy(conn)}


# --- Teilnehmer --------------------------------------------------------------

@app.route("/")
def participants():
    with storage.connect() as conn:
        return render_template("participants.html", people=storage.list_participants(conn))


@app.post("/participants/add")
def participant_add():
    name, email = request.form.get("name", "").strip(), request.form.get("email", "").strip()
    if not name or "@" not in email:
        flash("Bitte Name und gültige E-Mail angeben.", "error")
        return redirect(url_for("participants"))
    try:
        with storage.connect() as conn:
            storage.add_participant(conn, name, email)
        flash(f"{name} hinzugefügt.", "ok")
    except sqlite3.IntegrityError:
        flash("Diese E-Mail-Adresse ist bereits eingetragen.", "error")
    return redirect(url_for("participants"))


@app.post("/participants/<int:pid>/delete")
def participant_delete(pid):
    with storage.connect() as conn:
        storage.delete_participant(conn, pid)
    flash("Teilnehmer entfernt.", "ok")
    return redirect(url_for("participants"))


# --- Haushalts-Matrix --------------------------------------------------------

@app.route("/households", methods=["GET", "POST"])
def households():
    with storage.connect() as conn:
        if request.method == "POST":
            pairs = []
            for field in request.form.getlist("pair"):
                a, b = field.split("-")
                pairs.append((int(a), int(b)))
            storage.save_households(conn, pairs)
            flash("Haushalte gespeichert.", "ok")
            return redirect(url_for("households"))
        return render_template("households.html",
                               people=storage.list_participants(conn),
                               pairs=storage.household_pairs(conn))


# --- E-Mail-Vorlagen ---------------------------------------------------------

TEMPLATES = {"mail": "Zuteilung", "reminder": "Erinnerung"}


@app.route("/template", methods=["GET", "POST"])
def mail_template():
    with storage.connect() as conn:
        if request.method == "POST":
            which = request.form["which"]
            if which in TEMPLATES:
                storage.set_setting(conn, f"{which}_subject", request.form["subject"])
                storage.set_setting(conn, f"{which}_body", request.form["body"])
                flash(f"Vorlage „{TEMPLATES[which]}“ gespeichert.", "ok")
            return redirect(url_for("mail_template"))

        sample = {"name": "Anna", "partner": "Ben", "jahr": datetime.date.today().year}
        templates = []
        for key, title in TEMPLATES.items():
            subject = storage.get_setting(conn, f"{key}_subject")
            body = storage.get_setting(conn, f"{key}_body")
            templates.append({"key": key, "title": title, "subject": subject, "body": body,
                              "preview_subject": mailer.render(subject, **sample),
                              "preview_body": mailer.render(body, **sample)})
    return render_template("template.html", templates=templates)


# --- Auslosung ---------------------------------------------------------------

@app.route("/draw", methods=["GET", "POST"])
def draw_page():
    year_default = datetime.date.today().year
    with storage.connect() as conn:
        if request.method == "POST":
            action = request.form["action"]
            year = int(request.form.get("year", year_default))
            try:
                if action == "lookback":
                    storage.set_setting(conn, "lookback_years", str(int(request.form["lookback"])))
                    flash("Sperrzeitraum gespeichert.", "ok")
                elif action == "delete":
                    storage.delete_draw(conn, year)
                    flash(f"Auslosung {year} gelöscht.", "ok")
                elif action == "check":
                    result = compute_draw(conn, year)
                    flash(f"Testlauf erfolgreich: Auslosung für {len(result)} Personen ist möglich "
                          "(nichts gespeichert, nichts versendet).", "ok")
                elif action == "run":
                    flash(perform_draw(conn, year), "ok")
                elif action == "resend":
                    flash(f"Zuteilung {year}: " + send_for_year(conn, year, "mail"), "ok")
                elif action == "remind":
                    flash(f"Erinnerung {year}: " + send_for_year(conn, year, "reminder"), "ok")
            except ActionError as e:
                flash(str(e), "error")
            except Exception as e:  # noqa: BLE001 – z. B. SMTP-Fehler anzeigen
                flash(f"E-Mail-Versand fehlgeschlagen: {e}", "error")
            return redirect(url_for("draw_page"))

        return render_template("draw.html", year=year_default,
                               count=len(storage.list_participants(conn)),
                               lookback=storage.get_setting(conn, "lookback_years"),
                               history=storage.draw_overview(conn))


# --- Zeitplan ----------------------------------------------------------------

def _rule_from_form(form):
    mode = form["mode"]
    if form["kind"] not in ("draw", "reminder") or mode not in rules.MODES or not form.get("time"):
        raise ValueError
    month = int(form["month"]) if mode != "advent" else 12
    nth = int(form["advent_nth"] if mode == "advent" else form["nth"])
    weekday = int(form["weekday"]) if mode == "nth_weekday" else None
    day = int(form["day"]) if mode == "fixed_date" else None
    if not (1 <= month <= 12) or (day is not None and not 1 <= day <= 31):
        raise ValueError
    return {"kind": form["kind"], "mode": mode, "month": month, "nth": nth,
            "weekday": weekday, "day": day, "time": form["time"]}


@app.route("/schedule", methods=["GET", "POST"])
def schedule():
    with storage.connect() as conn:
        if request.method == "POST":
            if request.form["action"] == "add_rule":
                try:
                    rule = _rule_from_form(request.form)
                except (KeyError, ValueError):
                    flash("Bitte die Regel vollständig ausfüllen.", "error")
                    return redirect(url_for("schedule"))
                storage.add_rule(conn, created_at=scheduler.now_local(), **rule)
                scheduler.materialize_rules(conn, scheduler.now_local())
                flash(f"Jährlicher Termin angelegt: {rules.describe(rule)}.", "ok")
            elif request.form["action"] == "delete_rule":
                storage.delete_rule(conn, int(request.form["rule_id"]))
                flash("Jährlicher Termin gelöscht.", "ok")
            elif request.form["action"] == "add":
                kind, run_at = request.form["kind"], request.form["run_at"]
                if kind not in ("draw", "reminder") or not run_at:
                    flash("Bitte Art und Zeitpunkt angeben.", "error")
                else:
                    storage.add_job(conn, kind, int(request.form["year"]), run_at)
                    flash("Termin angelegt.", "ok")
            elif request.form["action"] == "delete":
                storage.delete_job(conn, int(request.form["job_id"]))
                flash("Termin gelöscht.", "ok")
            return redirect(url_for("schedule"))
        now = scheduler.now_local()
        rule_rows = [{"id": r["id"], "kind": r["kind"], "text": rules.describe(r),
                      "next": rules.next_occurrence(r, now)} for r in storage.list_rules(conn)]
        return render_template("schedule.html", jobs=storage.list_jobs(conn), rules=rule_rows,
                               year=datetime.date.today().year, now=now, tz=scheduler.TZ.key,
                               weekdays=rules.WEEKDAYS, months=rules.MONTHS, nths=rules.NTH)


# --- Einstellungen -----------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    with storage.connect() as conn:
        if request.method == "POST":
            if request.form["action"] == "save":
                mailer.save_smtp_config(conn, request.form)
                flash("SMTP-Einstellungen gespeichert.", "ok")
            elif request.form["action"] == "test":
                to = request.form.get("to", "").strip()
                try:
                    mailer.send_test(conn, to)
                    where = "in data/outbox abgelegt (Dummy-Modus)" if mailer.is_dummy(conn) else f"an {to} versendet"
                    flash(f"Test-E-Mail {where}.", "ok")
                except Exception as e:  # noqa: BLE001
                    flash(f"Test-E-Mail fehlgeschlagen: {e}", "error")
            return redirect(url_for("settings"))
        cfg = mailer.smtp_config(conn)
        return render_template("settings.html", cfg=cfg, has_password=bool(cfg.pop("password")))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=True)
