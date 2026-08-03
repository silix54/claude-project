"""Build one state object. The HTML dashboard and the Claude brief both read
this and nothing else, so they can never disagree about the facts."""

from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from . import db, gcal, gtasks as T, strava
from .periodization import cycle_state, upcoming_deloads, days_until

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _cfg(name):
    return yaml.safe_load(Path(f"config/{name}.yaml").read_text())


def training_state(cfg, today: date):
    p = cfg["periodization"]
    st = cycle_state(today, p["anchor"], p["build_weeks"], p["deload_weeks"])
    planned = cfg["week"].get(DAYS[today.weekday()], [])
    if st.is_deload:
        planned = [dict(s, deload=True) for s in planned
                   if not (cfg["deload_rules"]["drop_intervals"]
                           and s.get("zone") == 4)]
    return st, planned


def compliance(session_dates: set[date], days: int = 7):
    """Sessions logged in the trailing window, and consecutive-day streak.
    session_dates is the union of Strava cardio days and quick-add strength
    log days — that union is "a session happened," which is what the streak
    and the overtraining guard both actually care about."""
    if not session_dates:
        return {"logged": 0, "streak": 0, "last": None}
    ds = sorted(session_dates)
    cutoff = date.today() - timedelta(days=days)
    logged = len([d for d in ds if d >= cutoff])
    streak, cur = 0, date.today()
    while cur in session_dates:
        streak += 1
        cur -= timedelta(days=1)
    return {"logged": logged, "streak": streak, "last": ds[-1].isoformat()}


def deadline_pressure(horizon_days: int = 21):
    """Course deadlines live in the deadlines table (settings-editable), not
    term.yaml — only the term's own start/end/exam/reading-week dates stay
    in the YAML file, since those change once a term rather than as syllabi
    land through the term."""
    out = []
    today = date.today()
    for d in db.list_deadlines():
        due = date.fromisoformat(d["due"])
        n = (due - today).days
        if -3 <= n <= horizon_days:
            out.append({"course": d["course"], "title": d["title"], "due": due,
                        "days": n, "weight": d.get("weight"),
                        "est_hours": d.get("est_hours")})
    return sorted(out, key=lambda x: x["due"])


def collisions(term_cfg, train_cfg, weeks: int = 8):
    """Weeks where deadlines, reserve weekends, races, and deloads stack.
    This is the whole point of the thing. Catch November in September."""
    today = date.today()
    p = train_cfg["periodization"]
    horizon = today + timedelta(weeks=weeks)
    deloads = set(upcoming_deloads(p["anchor"], horizon, p["build_weeks"],
                                   p["deload_weeks"], today))
    buckets: dict[date, dict] = {}

    def wk(d):
        return d - timedelta(days=d.weekday())

    for d in deadline_pressure(horizon_days=weeks * 7):
        b = buckets.setdefault(wk(d["due"]), {"deadlines": [], "flags": []})
        b["deadlines"].append(d)
    for pair in (term_cfg.get("reserve_weekends") or []):
        s = pair[0] if isinstance(pair[0], date) else date.fromisoformat(str(pair[0]))
        if today <= s <= horizon:
            buckets.setdefault(wk(s), {"deadlines": [], "flags": []})["flags"].append("reserve weekend")
    for r in train_cfg.get("races", []):
        rd = r["date"] if isinstance(r["date"], date) else date.fromisoformat(str(r["date"]))
        if today <= rd <= horizon:
            buckets.setdefault(wk(rd), {"deadlines": [], "flags": []})["flags"].append(
                f"race: {r['name']}")
    rw = term_cfg["term"].get("reading_week")
    if rw:
        s = rw[0] if isinstance(rw[0], date) else date.fromisoformat(str(rw[0]))
        if today <= s <= horizon:
            buckets.setdefault(wk(s), {"deadlines": [], "flags": []})["flags"].append("reading week")

    out = []
    for w in sorted(buckets):
        b = buckets[w]
        load = sum(d.get("est_hours") or 4 for d in b["deadlines"])
        if w in deloads:
            b["flags"].append("training deload")
        severity = "high" if (len(b["deadlines"]) >= 3 or load >= 18
                              or (len(b["deadlines"]) >= 2 and b["flags"])) else \
                   "watch" if (len(b["deadlines"]) >= 2 or load >= 10) else "clear"
        out.append({"week_of": w, "deadlines": b["deadlines"], "flags": b["flags"],
                    "est_hours": load, "severity": severity})
    return out


def build(today: date | None = None) -> dict:
    today = today or date.today()
    term, train = _cfg("term"), _cfg("training")
    wake, sleep = db.wake_sleep()

    events, cal_live = gcal.fetch(days=21)
    todays = [e for e in gcal.on_day(events, today)]
    windows = gcal.gaps(events, today, wake=wake, sleep=sleep)

    tl = T.load()
    activities, strava_live = strava.fetch(days=14)
    st, planned = training_state(train, today)

    upcoming = [e for e in events if today < e.start.date() <= today + timedelta(days=7)]
    session_dates = strava.cardio_dates(activities) | {
        date.fromisoformat(r["date"]) for r in db.strength_logs(today - timedelta(days=60))}

    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "date": today,
        "calendar_live": cal_live,
        "strava_live": strava_live,
        "wake": wake,
        "sleep": sleep,
        "term": term["term"],
        "events_today": todays,
        "events_week": upcoming,
        "gaps": windows,
        "free_minutes": sum(int((b - a).total_seconds() // 60) for a, b in windows),
        "tasks_all": tl,
        "slate": T.today_slate(tl),
        "open_count": len(T.open_tasks(tl)),
        "overdue": [t for t in tl if t.overdue],
        "stalled": T.stalled_tasks(tl),
        "committed_minutes": T.committed_minutes(tl),
        "cycle": st,
        "planned_sessions": planned,
        "deload_rules": train["deload_rules"],
        "nutrition": train["nutrition"],
        "guards": db.guards(),
        "compliance": compliance(session_dates),
        "recent_activities": activities[-5:],
        "weight_log": db.weight_logs(today - timedelta(days=60)),
        "deadlines": deadline_pressure(),
        "collisions": collisions(term, train),
        "weekly_focus": db.weekly_focus(),
        "races": [{"name": r["name"],
                   "date": r["date"] if isinstance(r["date"], date)
                   else date.fromisoformat(str(r["date"])),
                   "days": days_until(r["date"] if isinstance(r["date"], date)
                                      else date.fromisoformat(str(r["date"])), today)}
                  for r in train["races"]
                  if days_until(r["date"] if isinstance(r["date"], date)
                                else date.fromisoformat(str(r["date"])), today) >= 0],
    }
