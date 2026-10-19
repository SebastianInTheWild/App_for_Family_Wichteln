"""Wichtel-App: Gruppen, Teilnehmer, Haushalts-Matrix, E-Mail-Vorlagen, Auslosung, Zeitplan, Einstellungen."""
import datetime
import hmac
import os
import sqlite3

from flask import (Flask, Response, flash, g, redirect, render_template, request, session,
                   url_for)

import generator
import importer
import mailer
import rules
import scheduler
import storage
from actions import (KIND_TITLES, ActionError, compute_draw, perform_draw, send_for_year,
                     send_test)

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


@app.before_request
def load_group():
    """Aktuelle Gruppe aus der Sitzung; fehlt sie (oder wurde gelöscht), gilt die erste."""
    if request.endpoint == "static":
        return
    with storage.connect() as conn:
        g.groups = storage.list_groups(conn)
        g.group = next((x for x in g.groups if x["id"] == session.get("group")), g.groups[0])
        g.gid = g.group["id"]
        g.dummy_mail = mailer.is_dummy(conn)


@app.context_processor
def inject_globals():
    return {"groups": g.get("groups", []), "group": g.get("group"),
            "dummy_mail": g.get("dummy_mail", False)}


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("favicon.ico")


# --- Gruppen ------------------------------------------------------------------

@app.post("/group/select")
def group_select():
    session["group"] = int(request.form["group"])
    return redirect(request.form.get("next") or url_for("persons"))


@app.route("/groups", methods=["GET", "POST"])
def groups():
    """Gruppenverwaltung – angezeigt als Abschnitt der Einstellungen."""
    if request.method == "POST":
        action, name = request.form["action"], request.form.get("name", "").strip()
        mail_name = request.form.get("mail_name", "")
        try:
            with storage.connect() as conn:
                if action == "add" and name:
                    session["group"] = storage.add_group(conn, name, mail_name)
                    flash(f"Gruppe „{name}“ angelegt und ausgewählt.", "ok")
                elif action == "save" and name:
                    storage.update_group(conn, int(request.form["group_id"]), name, mail_name)
                    flash("Gruppe gespeichert.", "ok")
                elif action == "delete":
                    if len(g.groups) <= 1:
                        flash("Die letzte Gruppe kann nicht gelöscht werden.", "error")
                    else:
                        storage.delete_group(conn, int(request.form["group_id"]))
                        session.pop("group", None)
                        flash("Gruppe mit allen Teilnahmen, Auslosungen und Terminen gelöscht (Personen bleiben in der Liste).", "ok")
        except sqlite3.IntegrityError:
            flash("Eine Gruppe mit diesem Namen gibt es schon.", "error")
    return redirect(url_for("settings", _anchor="gruppen"))


# --- Teilnehmer --------------------------------------------------------------

def _selected_groups(form):
    valid = {x["id"] for x in g.groups}
    return [int(x) for x in form.getlist("groups") if int(x) in valid]


@app.route("/persons", methods=["GET", "POST"])
def persons():
    if request.method == "GET":
        with storage.connect() as conn:
            return render_template("persons.html", people=storage.list_persons(conn))

    action, form = request.form["action"], request.form
    if action == "add":
        name, email = form.get("name", "").strip(), form.get("email", "").strip()
        if not name or "@" not in email:
            flash("Bitte Name und gültige E-Mail angeben.", "error")
            return redirect(url_for("persons"))
        with storage.connect() as conn:
            person_id, created = storage.add_person(conn, name, email)
            assigned = sum(storage.add_members(conn, gid, [person_id]) for gid in _selected_groups(form))
        if created:
            flash(f"{name} angelegt.", "ok")
        elif assigned:
            flash("Diese E-Mail gibt es schon – die vorhandene Person wurde den gewählten Gruppen zugeordnet.", "ok")
        else:
            flash("Diese E-Mail gibt es schon in der Personenliste.", "error")

    elif action == "save":
        # Eine Zeile je Person: Name, E-Mail und Häkchen je Gruppe
        try:
            with storage.connect() as conn:
                valid = {x["id"] for x in g.groups}
                for pid in map(int, form.getlist("person_id")):
                    name = form.get(f"name_{pid}", "").strip()
                    email = form.get(f"email_{pid}", "").strip()
                    if not name or "@" not in email:
                        raise ValueError(f"Ungültiger Name oder E-Mail bei „{name or email}“.")
                    storage.update_person(conn, pid, name, email)
                    storage.set_memberships(conn, pid, {int(x) for x in form.getlist(f"groups_{pid}")
                                                        if int(x) in valid})
            flash("Personenliste gespeichert.", "ok")
        except sqlite3.IntegrityError:
            flash("Nicht gespeichert: Eine E-Mail-Adresse kommt doppelt vor.", "error")
        except ValueError as e:
            flash(f"Nicht gespeichert: {e}", "error")

    elif action == "delete":
        with storage.connect() as conn:
            storage.delete_person(conn, int(form["delete_id"]))
        flash("Person aus der Liste und allen Gruppen gelöscht.", "ok")

    elif action == "import":
        text = form.get("text", "")
        upload = request.files.get("file")
        if upload and upload.filename:
            text += "\n" + importer.decode(upload.read())
        people, invalid = importer.parse(text)
        if not people and not invalid:
            flash("Bitte eine Datei auswählen oder Zeilen einfügen.", "error")
            return redirect(url_for("persons"))
        with storage.connect() as conn:
            created, skipped, assigned = storage.import_persons(conn, people, _selected_groups(form))
        flash(f"Import: {created} neu, {skipped} schon vorhanden/doppelt übersprungen"
              + (f", {assigned} Gruppen-Zuordnungen" if assigned else "") + ".", "ok")
        if invalid:
            flash(f"{len(invalid)} Zeile(n) ohne gültige E-Mail ignoriert: "
                  + "; ".join(invalid[:5]) + (" …" if len(invalid) > 5 else ""), "error")
    return redirect(url_for("persons"))


@app.route("/")
def index():
    return redirect(url_for("persons"))


# --- Haushalts-Matrix --------------------------------------------------------

@app.route("/households", methods=["GET", "POST"])
def households():
    with storage.connect() as conn:
        if request.method == "POST":
            pairs = []
            for field in request.form.getlist("pair"):
                a, b = field.split("-")
                pairs.append((int(a), int(b)))
            storage.save_households(conn, g.gid, pairs)
            flash("Haushalte gespeichert.", "ok")
            return redirect(url_for("households"))
        return render_template("households.html",
                               people=storage.list_participants(conn, g.gid),
                               pairs=storage.household_pairs(conn, g.gid))


# --- E-Mail-Vorlagen ---------------------------------------------------------

@app.route("/template", methods=["GET", "POST"])
def mail_template():
    with storage.connect() as conn:
        if request.method == "POST":
            action, form = request.form["action"], request.form
            if action == "generate" and form.get("kind") in KIND_TITLES:
                t = generator.generate(form["kind"])
                tid = storage.add_template(conn, form["kind"], t["title"], t["subject"], t["body"],
                                           active=False)
                flash(f"Neue Vorlage „{t['title']}“ erzeugt – bitte prüfen, ggf. anpassen "
                      "und dann „aktiv“ ankreuzen.", "ok")
                return redirect(url_for("mail_template", open=tid, _anchor=f"t{tid}"))
            if action == "add" and form.get("kind") in KIND_TITLES:
                tid = storage.add_template(conn, form["kind"], form["title"].strip() or "Neue Vorlage",
                                           form["subject"], form["body"])
                flash("Vorlage angelegt.", "ok")
                return redirect(url_for("mail_template", _anchor=f"t{tid}"))
            tid = int(form["template_id"])
            if action == "save":
                storage.update_template(conn, tid, form["title"].strip() or "Vorlage",
                                        form["subject"], form["body"], form.get("active"))
                flash("Vorlage gespeichert.", "ok")
            elif action == "delete":
                storage.delete_template(conn, tid)
                flash("Vorlage gelöscht.", "ok")
                return redirect(url_for("mail_template"))
            elif action == "test":
                to = form.get("to", "").strip()
                session["test_to"] = to
                try:
                    title = send_test(conn, to, g.gid, tid)
                    where = "in data/outbox abgelegt (Dummy-Modus)" if mailer.is_dummy(conn) else f"an {to} versendet"
                    flash(f"Test-E-Mail „{title}“ {where}.", "ok")
                except Exception as e:  # noqa: BLE001
                    flash(f"Test-E-Mail fehlgeschlagen: {e}", "error")
            return redirect(url_for("mail_template", _anchor=f"t{tid}"))

        year = datetime.date.today().year
        gruppe, header = mailer.mail_identity(g.group, year)
        sample = {"name": "Anna", "partner": "Ben", "jahr": year, "gruppe": gruppe}
        sections = []
        for kind, title in KIND_TITLES.items():
            items = []
            for t in storage.list_templates(conn, kind):
                subject, _, html_body = mailer.compose(t, sample, header=header)
                items.append({"t": t, "preview_subject": subject, "preview_html": html_body})
            sections.append({"kind": kind, "title": title, "entries": items,
                             "active": sum(1 for i in items if i["t"]["active"])})
    return render_template("template.html", sections=sections, test_to=session.get("test_to", ""),
                           open_id=request.args.get("open", type=int))


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
                    storage.set_lookback(conn, g.gid, int(request.form["lookback"]))
                    flash("Sperrzeitraum gespeichert.", "ok")
                elif action == "delete":
                    storage.delete_draw(conn, g.gid, year)
                    flash(f"Auslosung {year} gelöscht.", "ok")
                elif action == "check":
                    result = compute_draw(conn, g.gid, year)
                    flash(f"Testlauf erfolgreich: Auslosung für {len(result)} Personen ist möglich "
                          "(nichts gespeichert, nichts versendet).", "ok")
                elif action == "run":
                    flash(perform_draw(conn, g.gid, year), "ok")
                elif action == "resend":
                    flash(f"Zuteilung {year}: " + send_for_year(conn, g.gid, year, "mail"), "ok")
                elif action == "remind":
                    flash(f"Erinnerung {year}: " + send_for_year(conn, g.gid, year, "reminder"), "ok")
            except ActionError as e:
                flash(str(e), "error")
            except Exception as e:  # noqa: BLE001 – z. B. SMTP-Fehler anzeigen
                flash(f"E-Mail-Versand fehlgeschlagen: {e}", "error")
            return redirect(url_for("draw_page"))

        return render_template("draw.html", year=year_default,
                               count=len(storage.list_participants(conn, g.gid)),
                               lookback=g.group["lookback_years"],
                               history=storage.draw_overview(conn, g.gid))


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
                storage.add_rule(conn, g.gid, created_at=scheduler.now_local(), **rule)
                scheduler.materialize_rules(conn, scheduler.now_local())
                flash(f"Jährlicher Termin angelegt: {rules.describe(rule)}.", "ok")
            elif request.form["action"] == "delete_rule":
                storage.delete_rule(conn, g.gid, int(request.form["rule_id"]))
                flash("Jährlicher Termin gelöscht.", "ok")
            elif request.form["action"] == "add":
                kind, run_at = request.form["kind"], request.form["run_at"]
                if kind not in ("draw", "reminder") or not run_at:
                    flash("Bitte Art und Zeitpunkt angeben.", "error")
                else:
                    storage.add_job(conn, g.gid, kind, int(request.form["year"]), run_at)
                    flash("Termin angelegt.", "ok")
            elif request.form["action"] == "delete":
                storage.delete_job(conn, g.gid, int(request.form["job_id"]))
                flash("Termin gelöscht.", "ok")
            return redirect(url_for("schedule"))
        now = scheduler.now_local()
        rule_rows = [{"id": r["id"], "kind": r["kind"], "text": rules.describe(r),
                      "next": rules.next_occurrence(r, now)}
                     for r in storage.list_rules(conn, g.gid)]
        return render_template("schedule.html", jobs=storage.list_jobs(conn, g.gid),
                               rules=rule_rows, year=datetime.date.today().year, now=now,
                               tz=scheduler.TZ.key, weekdays=rules.WEEKDAYS,
                               months=rules.MONTHS, nths=rules.NTH)


# --- Einstellungen -----------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    with storage.connect() as conn:
        if request.method == "POST":
            if request.form["action"] == "save":
                mailer.save_smtp_config(conn, request.form)
                flash("SMTP-Einstellungen gespeichert.", "ok")
                warning = mailer.check_combination(request.form)
                if warning:
                    flash(warning, "error")
            elif request.form["action"] == "test":
                to = request.form.get("to", "").strip()
                session["test_to"] = to
                try:
                    title = send_test(conn, to, g.gid)
                    where = "in data/outbox abgelegt (Dummy-Modus)" if mailer.is_dummy(conn) else f"an {to} versendet"
                    flash(f"Test-E-Mail (Vorlage „{title}“) {where}.", "ok")
                except Exception as e:  # noqa: BLE001
                    flash(f"Test-E-Mail fehlgeschlagen: {e}", "error")
            return redirect(url_for("settings"))
        cfg = mailer.smtp_config(conn)
        year = datetime.date.today().year
        return render_template("settings.html", cfg=cfg, has_password=bool(cfg.pop("password")),
                               test_to=session.get("test_to", ""), year=year,
                               previews={x["id"]: mailer.mail_identity(x, year)[1] for x in g.groups})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=True)
