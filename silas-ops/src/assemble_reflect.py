"""State assembly for /reflect, gluing db.py + reflect.py + render_reflect.py
together into one dict the route can render. Split out from assemble.py
because this is a distinct view with its own cadence — see the module
docstring in render_reflect.py."""

from __future__ import annotations
from datetime import date, timedelta

from . import db, journal, reflect
from .render_reflect import habit_heatmap, habit_toggle_row, mood_chart, correlation_summary

HEATMAP_WEEKS = 12


def build_reflect(today: date | None = None) -> dict:
    today = today or date.today()
    since = today - timedelta(weeks=HEATMAP_WEEKS)

    habits = db.list_habits()
    logs_by_habit = {h["id"]: db.habit_logs(h["id"], since) for h in habits}
    done_today = {h["id"]: logs_by_habit[h["id"]].get(today.isoformat(), False) for h in habits}

    mood_rows = db.mood_logs(today - timedelta(days=45))
    stability_rows = reflect.rolling_stability(mood_rows)
    links = reflect.all_links(habits, mood_rows, since, db.habit_logs)

    devo = db.devotions_logs(today)
    done_today_devo = any(r["date"] == today.isoformat() and r["done"] for r in devo)
    streak, cur = 0, today
    all_devo = {r["date"]: bool(r["done"]) for r in db.devotions_logs(today - timedelta(days=400))}
    while all_devo.get(cur.isoformat()):
        streak += 1
        cur -= timedelta(days=1)

    return {
        "heatmap": habit_heatmap(habits, logs_by_habit, weeks=HEATMAP_WEEKS),
        "habit_toggles": habit_toggle_row(habits, done_today),
        "mood_chart": mood_chart(stability_rows),
        "correlation": correlation_summary(links),
        "devotions_done_today": done_today_devo,
        "devotions_streak": streak,
        "mood_logged_today": any(r["date"] == today.isoformat() for r in mood_rows),
        "journal_prompts": journal.todays_prompts(),
    }
