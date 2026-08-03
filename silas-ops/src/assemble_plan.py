"""State assembly for /plan — the Sunday session. A guided review of the
last 7 days, a tighter look at the next 7, live triage of every open task,
and a place to commit 1-3 priorities that the daily view reads all week.

Deliberately separate from assemble.build(): the daily view is a ten-second
glance and this is a longer, once-a-week look. Sharing one state object
between them would blur that boundary.
"""

from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import db, gcal, gtasks as T, strava
from .assemble import training_state, compliance, deadline_pressure
from .periodization import cycle_state, monday_of


def _cfg(name):
    return yaml.safe_load(Path(f"config/{name}.yaml").read_text())


def review(today: date, train_cfg: dict) -> dict:
    week_ago = today - timedelta(days=7)
    activities, _ = strava.fetch(days=14)
    session_dates = strava.cardio_dates(activities) | {
        date.fromisoformat(r["date"]) for r in db.strength_logs(week_ago)}

    planned_days = 0
    for i in range(7):
        d = week_ago + timedelta(days=1 + i)
        _, planned = training_state(train_cfg, d)
        if any(s.get("type") != "rest" for s in planned):
            planned_days += 1
    logged_days = len([d for d in session_dates if week_ago < d <= today])
    comp = compliance(session_dates)
    guard_tripped = comp["streak"] >= db.guards()["max_consecutive_training_days"]

    tasks = T.load()
    completed = T.completed_since(tasks, week_ago)
    stalled = T.stalled_tasks(tasks)

    return {
        "planned_days": planned_days, "logged_days": logged_days,
        "guard_tripped": guard_tripped, "streak": comp["streak"],
        "tasks_completed": len(completed), "stalled": stalled,
        "recent_weight": db.weight_logs(week_ago),
    }


def ahead(today: date, term_cfg: dict, train_cfg: dict) -> dict:
    next_monday = monday_of(today + timedelta(days=1))
    next_sunday = next_monday + timedelta(days=6)

    events, _ = gcal.fetch(days=14)
    week_events = [e for e in events if next_monday <= e.start.date() <= next_sunday]
    load_minutes = sum(e.minutes for e in week_events if not e.all_day)

    due_this_week = [d for d in deadline_pressure(horizon_days=7) if d["days"] >= 0]

    p = train_cfg["periodization"]
    st = cycle_state(next_monday, p["anchor"], p["build_weeks"], p["deload_weeks"])

    flags = []
    for pair in (term_cfg.get("reserve_weekends") or []):
        s = pair[0] if isinstance(pair[0], date) else date.fromisoformat(str(pair[0]))
        if next_monday <= s <= next_sunday:
            flags.append("reserve weekend")
    for r in train_cfg.get("races", []):
        rd = r["date"] if isinstance(r["date"], date) else date.fromisoformat(str(r["date"]))
        if next_monday <= rd <= next_sunday:
            flags.append(f"race: {r['name']}")
    if st.is_deload:
        flags.append("deload week")

    return {"week_of": next_monday, "load_minutes": load_minutes,
           "event_count": len(week_events), "deadlines": due_this_week,
           "cycle_label": st.label, "flags": flags}


def build_plan(today: date | None = None) -> dict:
    today = today or date.today()
    term, train = _cfg("term"), _cfg("training")
    tasks = T.load()
    return {
        "date": today,
        "review": review(today, train),
        "ahead": ahead(today, term, train),
        "triage_tasks": T.open_tasks(tasks),
        "by_quadrant": T.open_by_quadrant(tasks),
        "weekly_focus": db.weekly_focus(),
    }
