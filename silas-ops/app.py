"""Flask entrypoint. Routes only — all real logic lives in src/. Each route
either renders a full page (the daily view, /plan, /reflect, /settings) or
handles a single htmx action and returns the fragment that changed.

No AI dependency anywhere here, per the build spec: every route below is
deterministic reads/writes against Calendar, Tasks, Strava, Drive, and the
local DB. The one allowed AI add-on (an optional daily-brief endpoint that
calls the Anthropic API) is not built — the spec says build it only if
asked, and it hasn't been.
"""

from __future__ import annotations
import os
import secrets as pysecrets
from datetime import date

from flask import Flask, jsonify, redirect, request, session, url_for

from src import auth, db, google_auth, gtasks, journal, push, strava
from src.assemble import build
from src.assemble_plan import build_plan
from src.assemble_reflect import build_reflect
from src.render import render, _tasks as render_tasks
from src.render_plan import render_plan, triage_list, commit_section
from src.render_reflect import render_reflect, devotions_block, mood_form
from src.render_settings import render_settings

LOGIN_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ops</title>
<style>body{{background:#E8E6E1;color:#16181D;font:15px/1.5 monospace;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
form{{display:flex;flex-direction:column;gap:10px;width:240px}}
input{{font:15px monospace;padding:10px;border:1px solid #C9C5BC;background:#fff}}
button{{font:13px monospace;text-transform:uppercase;letter-spacing:.08em;padding:10px;
background:#16181D;color:#E8E6E1;border:none;cursor:pointer}}
.err{{color:#A8431C;font-size:12px}}</style></head><body>
<form method="post">{error}
<input type="password" name="password" placeholder="password" autofocus required>
<button type="submit">Enter</button></form></body></html>"""


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or pysecrets.token_hex(32)
    db.init()

    @app.errorhandler(google_auth.NotAuthorized)
    def not_authorized(e):
        return (f'<p class="sub" style="color:#A8431C">Not connected to Google yet — '
               f'<a href="/oauth/google/start">connect</a>.</p>', 409)

    # ---- auth -------------------------------------------------------------

    @app.get("/login")
    def login_form():
        return LOGIN_PAGE.format(error="")

    @app.post("/login")
    def login():
        try:
            ok = auth.check_password(request.form.get("password", ""))
        except RuntimeError:
            return LOGIN_PAGE.format(error='<p class="err">APP_PASSWORD not configured server-side.</p>')
        if ok:
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("daily"))
        return LOGIN_PAGE.format(error='<p class="err">Wrong password.</p>')

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login_form"))

    # ---- daily view ---------------------------------------------------------

    @app.get("/")
    @auth.login_required
    def daily():
        return render(build())

    # ---- quick-add ------------------------------------------------------------

    @app.post("/quickadd/task")
    @auth.login_required
    def quickadd_task():
        due = date.fromisoformat(request.form["due"]) if request.form.get("due") else None
        est = int(request.form["est_minutes"]) if request.form.get("est_minutes") else None
        gtasks.create_task(request.form["title"], tag=request.form.get("tag") or None,
                           quadrant=request.form.get("quadrant") or None,
                           est_minutes=est, due=due)
        return render_tasks(build())

    @app.post("/quickadd/strength")
    @auth.login_required
    def quickadd_strength():
        f = request.form
        db.log_strength(f["exercise"], int(f["sets"]) if f.get("sets") else None,
                        int(f["reps"]) if f.get("reps") else None,
                        float(f["weight_lb"]) if f.get("weight_lb") else None)
        return '<p class="sub">Logged.</p>'

    # ---- /plan ----------------------------------------------------------------

    @app.get("/plan")
    @auth.login_required
    def plan():
        return render_plan(build_plan())

    @app.post("/plan/triage/<task_id>")
    @auth.login_required
    def plan_triage(task_id):
        action = request.args.get("action")
        tasks = gtasks.load()
        t = next((x for x in tasks if x.id == task_id), None)
        if t:
            if action == "push":
                gtasks.push_due_by_days(task_id, t.due, days=7)
            elif action == "drop":
                gtasks.patch_meta(task_id, t.tag, "drop", t.est_minutes)
            elif action == "keep" and not t.due:
                from src.periodization import monday_of
                from datetime import timedelta
                gtasks.set_due(task_id, monday_of(date.today()) + timedelta(days=6))
        return f'<li id="triage-{task_id}" style="opacity:.4">triaged — {action}</li>'

    @app.post("/plan/commit")
    @auth.login_required
    def plan_commit():
        f = request.form
        priorities = [p.strip() for p in (f.get("p1", ""), f.get("p2", ""), f.get("p3", "")) if p.strip()]
        db.set_weekly_focus(priorities)
        return commit_section(priorities)

    @app.post("/plan/weight")
    @auth.login_required
    def plan_weight():
        db.log_weight(float(request.form["weight_lb"]), request.form.get("note", ""))
        return '<p class="sub">Logged.</p>'

    # ---- /reflect ---------------------------------------------------------

    @app.get("/reflect")
    @auth.login_required
    def reflect_view():
        return render_reflect(build_reflect())

    @app.post("/reflect/habit/<int:habit_id>/toggle")
    @auth.login_required
    def reflect_habit_toggle(habit_id):
        logs = db.habit_logs(habit_id, date.today())
        currently_done = logs.get(date.today().isoformat(), False)
        db.log_habit(habit_id, done=not currently_done)
        return "", 204

    @app.post("/reflect/mood")
    @auth.login_required
    def reflect_mood():
        f = request.form
        db.log_mood(int(f["mood"]), int(f["energy"]), f.get("tag", ""), f.get("note", ""))
        return "", 204

    @app.post("/reflect/devotions")
    @auth.login_required
    def reflect_devotions():
        db.log_devotions(request.form.get("passage", ""), request.form.get("note", ""))
        return devotions_block(True, _devotions_streak())

    @app.post("/reflect/journal")
    @auth.login_required
    def reflect_journal():
        responses = {}
        for key, val in request.form.items():
            if key.startswith("p") and key[1:].isdigit():
                responses[int(key[1:])] = val
        journal.save_entry(responses)
        return '<p class="sub">Saved.</p>'

    def _devotions_streak():
        from datetime import timedelta
        logs = {r["date"]: bool(r["done"]) for r in db.devotions_logs(date.today() - timedelta(days=400))}
        streak, cur = 0, date.today()
        while logs.get(cur.isoformat()):
            streak += 1
            cur -= timedelta(days=1)
        return streak

    # ---- /settings --------------------------------------------------------

    @app.get("/settings")
    @auth.login_required
    def settings_view():
        import yaml
        from pathlib import Path
        term = yaml.safe_load(Path("config/term.yaml").read_text())
        state = {
            "habits": db.list_habits(),
            "fixed_prompts": db.list_prompts("fixed"),
            "rotating_prompts": db.list_prompts("rotating"),
            "deadlines": db.list_deadlines(),
            "course_codes": [c["code"] for c in term.get("courses", [])],
            "priority_order": db.priority_order(),
            "guards": db.guards(),
            "wake_sleep": db.wake_sleep(),
        }
        return render_settings(state)

    @app.post("/settings/habits")
    @auth.login_required
    def settings_add_habit():
        db.add_habit(request.form["name"])
        return redirect(url_for("settings_view"))

    @app.post("/settings/habits/<int:habit_id>/rename")
    @auth.login_required
    def settings_rename_habit(habit_id):
        db.rename_habit(habit_id, request.form["name"])
        return redirect(url_for("settings_view"))

    @app.post("/settings/habits/<int:habit_id>/archive")
    @auth.login_required
    def settings_archive_habit(habit_id):
        db.archive_habit(habit_id)
        return redirect(url_for("settings_view"))

    @app.post("/settings/prompts")
    @auth.login_required
    def settings_add_prompt():
        db.add_prompt(request.form["kind"], request.form["text"])
        return redirect(url_for("settings_view"))

    @app.post("/settings/prompts/<int:prompt_id>/edit")
    @auth.login_required
    def settings_edit_prompt(prompt_id):
        db.edit_prompt(prompt_id, request.form["text"])
        return redirect(url_for("settings_view"))

    @app.post("/settings/prompts/<int:prompt_id>/archive")
    @auth.login_required
    def settings_archive_prompt(prompt_id):
        db.archive_prompt(prompt_id)
        return redirect(url_for("settings_view"))

    @app.post("/settings/deadlines")
    @auth.login_required
    def settings_add_deadline():
        f = request.form
        db.add_deadline(f["course"], f["title"], f["due"],
                        float(f["weight"]) if f.get("weight") else None,
                        float(f["est_hours"]) if f.get("est_hours") else None)
        return redirect(url_for("settings_view"))

    @app.post("/settings/deadlines/<int:deadline_id>/archive")
    @auth.login_required
    def settings_archive_deadline(deadline_id):
        db.archive_deadline(deadline_id)
        return redirect(url_for("settings_view"))

    @app.post("/settings/priority-order")
    @auth.login_required
    def settings_priority_order():
        order = [p.strip() for p in request.form["order"].split(",") if p.strip()]
        db.set_priority_order(order)
        return redirect(url_for("settings_view"))

    @app.post("/settings/guards")
    @auth.login_required
    def settings_guards():
        f = request.form
        db.set_guards({"max_consecutive_training_days": int(f["max_consecutive_training_days"]),
                      "min_sleep_hours": float(f["min_sleep_hours"]),
                      "flag_if_sessions_per_week_over": int(f["flag_if_sessions_per_week_over"])})
        return redirect(url_for("settings_view"))

    @app.post("/settings/wake-sleep")
    @auth.login_required
    def settings_wake_sleep():
        db.set_wake_sleep(request.form["wake"], request.form["sleep"])
        return redirect(url_for("settings_view"))

    # ---- Google OAuth -----------------------------------------------------

    @app.get("/oauth/google/start")
    @auth.login_required
    def google_oauth_start():
        redirect_uri = url_for("google_oauth_callback", _external=True)
        flow = google_auth.web_flow(redirect_uri)
        auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
        session["google_oauth_state"] = state
        return redirect(auth_url)

    @app.get("/oauth/google/callback")
    @auth.login_required
    def google_oauth_callback():
        redirect_uri = url_for("google_oauth_callback", _external=True)
        flow = google_auth.web_flow(redirect_uri)
        flow.fetch_token(authorization_response=request.url)
        google_auth.save_credentials(flow.credentials)
        return redirect(url_for("daily"))

    # ---- Strava OAuth -------------------------------------------------------

    @app.get("/oauth/strava/start")
    @auth.login_required
    def strava_oauth_start():
        redirect_uri = url_for("strava_oauth_callback", _external=True)
        return redirect(strava.authorize_url(redirect_uri))

    @app.get("/oauth/strava/callback")
    @auth.login_required
    def strava_oauth_callback():
        strava.exchange_code(request.args["code"])
        return redirect(url_for("daily"))

    # ---- push --------------------------------------------------------------

    @app.get("/push/vapid-public-key")
    @auth.login_required
    def push_key():
        return jsonify({"key": push.public_key()})

    @app.post("/push/subscribe")
    @auth.login_required
    def push_subscribe():
        sub = request.get_json()
        db.add_push_subscription(sub["endpoint"], sub["keys"]["p256dh"], sub["keys"]["auth"])
        return "", 204

    @app.post("/push/unsubscribe")
    @auth.login_required
    def push_unsubscribe():
        db.remove_push_subscription(request.get_json()["endpoint"])
        return "", 204

    # ---- misc ---------------------------------------------------------------

    @app.get("/healthz")
    def healthz():
        return "ok"

    push.start_background_loop(app)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
