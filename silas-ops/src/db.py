"""Everything editable from the phone lives here, not in a YAML file.

One file, <DATA_DIR>/ops.db. No server process, no extra dependency beyond
Python's built-in sqlite3. Safe for a single user hitting it from one
device at a time, which is the only case that matters here.

Why this exists instead of extending the YAML files: YAML is great for
"I open a text editor twice a term and change three lines." It's a bad
fit for "I add a new habit from my phone on a Tuesday." A database with
a settings page can be written to from a web form. A YAML file on a
server can't be edited by you without SSHing in, which defeats the
entire point of making this modular.

DATA_DIR defaults to "data" (this repo's original path, still what local
dev uses) but on Render points at the mounted persistent disk — see
render.yaml's `disk` block. Without that env var, ops.db would sit on
Render's default ephemeral filesystem and get wiped on every redeploy.
"""

from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

DB_PATH = Path(os.environ.get("DATA_DIR", "data")) / "ops.db"

DEFAULT_PRIORITY_ORDER = ["school", "work", "faith", "fitness", "relationships"]
DEFAULT_GUARDS = {"max_consecutive_training_days": 5, "min_sleep_hours": 7,
                   "flag_if_sessions_per_week_over": 11}
DEFAULT_WAKE, DEFAULT_SLEEP = "06:00", "22:30"

SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (date('now')),
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS habit_logs (
    habit_id INTEGER NOT NULL REFERENCES habits(id),
    date TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (habit_id, date)
);

CREATE TABLE IF NOT EXISTS mood_logs (
    date TEXT PRIMARY KEY,
    mood INTEGER,          -- 1-5
    energy INTEGER,        -- 1-5
    tag TEXT,               -- one free-text word, optional, your vocabulary
    note TEXT
);

CREATE TABLE IF NOT EXISTS journal_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('fixed','rotating')),
    text TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS journal_responses (
    date TEXT NOT NULL,
    prompt_id INTEGER NOT NULL REFERENCES journal_prompts(id),
    response TEXT NOT NULL,
    PRIMARY KEY (date, prompt_id)
);

CREATE TABLE IF NOT EXISTS devotions_logs (
    date TEXT PRIMARY KEY,
    done INTEGER NOT NULL DEFAULT 1,
    passage TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS weight_logs (
    date TEXT PRIMARY KEY,
    weight_lb REAL NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course TEXT NOT NULL,
    title TEXT NOT NULL,
    due TEXT NOT NULL,
    weight REAL,
    est_hours REAL,
    archived_at TEXT
);

-- Google Tasks has no creation timestamp (only updated/due/completed), so
-- "stalled 7+ days" can't be read off the API directly. We stamp the date
-- we first saw each task id and treat that as its age anchor instead.
CREATE TABLE IF NOT EXISTS task_seen (
    task_id TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL
);

-- No Hevy subscription, so strength sessions get a quick-add form instead
-- of an API pull. Cardio compliance comes from Strava; this table is the
-- other half of "sessions logged" for the Body section's streak.
CREATE TABLE IF NOT EXISTS strength_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL DEFAULT (date('now')),
    exercise TEXT NOT NULL,
    sets INTEGER,
    reps INTEGER,
    weight_lb REAL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (date('now'))
);
"""

DEFAULT_FIXED_PROMPTS = [
    "What am I grateful for right now?",
    "When was I emotionally disturbed? How did I respond?",
    "What do I need to talk about with others?",
]

DEFAULT_ROTATING_PROMPTS = [
    "If today had a headline, what would it be?",
    "What's a small win nobody else noticed?",
    "What made you laugh today?",
    "What's a question you're sitting with right now?",
    "Rate today 1-10, and why that number?",
    "Who crossed your mind today, and why?",
]


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    """Create tables and seed default prompts. Safe to call every startup."""
    with conn() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM journal_prompts LIMIT 1").fetchone():
            for i, t in enumerate(DEFAULT_FIXED_PROMPTS):
                c.execute("INSERT INTO journal_prompts (kind, text, position) VALUES (?,?,?)",
                         ("fixed", t, i))
            for i, t in enumerate(DEFAULT_ROTATING_PROMPTS):
                c.execute("INSERT INTO journal_prompts (kind, text, position) VALUES (?,?,?)",
                         ("rotating", t, i))
        for key, val in (("priority_order", DEFAULT_PRIORITY_ORDER),
                         ("guards", DEFAULT_GUARDS),
                         ("wake_time", DEFAULT_WAKE), ("sleep_time", DEFAULT_SLEEP)):
            if not c.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone():
                v = val if isinstance(val, str) else json.dumps(val)
                c.execute("INSERT INTO settings (key, value) VALUES (?,?)", (key, v))


# ---- habits -----------------------------------------------------------

def add_habit(name: str) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO habits (name) VALUES (?)", (name,))
        return cur.lastrowid


def rename_habit(habit_id: int, name: str):
    with conn() as c:
        c.execute("UPDATE habits SET name=? WHERE id=?", (name, habit_id))


def archive_habit(habit_id: int):
    with conn() as c:
        c.execute("UPDATE habits SET archived_at=date('now') WHERE id=?", (habit_id,))


def list_habits(include_archived=False):
    q = "SELECT * FROM habits" + ("" if include_archived else " WHERE archived_at IS NULL")
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY id")]


def log_habit(habit_id: int, d: date | None = None, done: bool = True):
    with conn() as c:
        c.execute("INSERT INTO habit_logs (habit_id, date, done) VALUES (?,?,?) "
                 "ON CONFLICT(habit_id, date) DO UPDATE SET done=excluded.done",
                 (habit_id, (d or date.today()).isoformat(), int(done)))


def habit_logs(habit_id: int, since: date):
    with conn() as c:
        rows = c.execute("SELECT date, done FROM habit_logs WHERE habit_id=? AND date>=?",
                         (habit_id, since.isoformat()))
        return {r["date"]: bool(r["done"]) for r in rows}


# ---- mood / energy ------------------------------------------------------

def log_mood(mood: int, energy: int, tag: str = "", note: str = "", d: date | None = None):
    assert 1 <= mood <= 5 and 1 <= energy <= 5, "mood and energy are 1-5"
    with conn() as c:
        c.execute("INSERT INTO mood_logs (date, mood, energy, tag, note) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(date) DO UPDATE SET mood=excluded.mood, energy=excluded.energy, "
                 "tag=excluded.tag, note=excluded.note",
                 ((d or date.today()).isoformat(), mood, energy, tag, note))


def mood_logs(since: date):
    with conn() as c:
        rows = c.execute("SELECT * FROM mood_logs WHERE date>=? ORDER BY date", (since.isoformat(),))
        return [dict(r) for r in rows]


# ---- journal --------------------------------------------------------------

def list_prompts(kind: str | None = None, include_archived: bool = False):
    q = "SELECT * FROM journal_prompts" if include_archived else \
        "SELECT * FROM journal_prompts WHERE archived_at IS NULL"
    args = ()
    if kind:
        q += (" AND" if "WHERE" in q else " WHERE") + " kind=?"
        args = (kind,)
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY position", args)]


def add_prompt(kind: str, text: str):
    with conn() as c:
        pos = c.execute("SELECT COALESCE(MAX(position),-1)+1 FROM journal_prompts WHERE kind=?",
                        (kind,)).fetchone()[0]
        c.execute("INSERT INTO journal_prompts (kind, text, position) VALUES (?,?,?)",
                 (kind, text, pos))


def edit_prompt(prompt_id: int, text: str):
    with conn() as c:
        c.execute("UPDATE journal_prompts SET text=? WHERE id=?", (text, prompt_id))


def archive_prompt(prompt_id: int):
    with conn() as c:
        c.execute("UPDATE journal_prompts SET archived_at=date('now') WHERE id=?", (prompt_id,))


def save_journal_response(prompt_id: int, response: str, d: date | None = None):
    with conn() as c:
        c.execute("INSERT INTO journal_responses (date, prompt_id, response) VALUES (?,?,?) "
                 "ON CONFLICT(date, prompt_id) DO UPDATE SET response=excluded.response",
                 ((d or date.today()).isoformat(), prompt_id, response))


# ---- devotions ------------------------------------------------------------

def log_devotions(passage: str = "", note: str = "", d: date | None = None, done: bool = True):
    with conn() as c:
        c.execute("INSERT INTO devotions_logs (date, done, passage, note) VALUES (?,?,?,?) "
                 "ON CONFLICT(date) DO UPDATE SET done=excluded.done, "
                 "passage=excluded.passage, note=excluded.note",
                 ((d or date.today()).isoformat(), int(done), passage, note))


def devotions_logs(since: date):
    with conn() as c:
        rows = c.execute("SELECT * FROM devotions_logs WHERE date>=? ORDER BY date",
                         (since.isoformat(),))
        return [dict(r) for r in rows]


# ---- generic settings -----------------------------------------------------

def get_setting(key: str, default=None):
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key: str, value: str):
    with conn() as c:
        c.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def priority_order() -> list[str]:
    return json.loads(get_setting("priority_order") or json.dumps(DEFAULT_PRIORITY_ORDER))


def set_priority_order(order: list[str]):
    set_setting("priority_order", json.dumps(order))


def guards() -> dict:
    return json.loads(get_setting("guards") or json.dumps(DEFAULT_GUARDS))


def set_guards(g: dict):
    set_setting("guards", json.dumps(g))


def wake_sleep() -> tuple[str, str]:
    return (get_setting("wake_time", DEFAULT_WAKE), get_setting("sleep_time", DEFAULT_SLEEP))


def set_wake_sleep(wake: str, sleep: str):
    set_setting("wake_time", wake)
    set_setting("sleep_time", sleep)


def weekly_focus() -> list[str]:
    return json.loads(get_setting("weekly_focus") or "[]")


def set_weekly_focus(priorities: list[str]):
    set_setting("weekly_focus", json.dumps(priorities[:3]))


# ---- course deadlines -------------------------------------------------

def add_deadline(course: str, title: str, due: str, weight: float | None = None,
                 est_hours: float | None = None) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO deadlines (course, title, due, weight, est_hours) "
                        "VALUES (?,?,?,?,?)", (course, title, due, weight, est_hours))
        return cur.lastrowid


def edit_deadline(deadline_id: int, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE deadlines SET {cols} WHERE id=?",
                 (*fields.values(), deadline_id))


def archive_deadline(deadline_id: int):
    with conn() as c:
        c.execute("UPDATE deadlines SET archived_at=date('now') WHERE id=?", (deadline_id,))


def list_deadlines(include_archived=False):
    q = "SELECT * FROM deadlines" + ("" if include_archived else " WHERE archived_at IS NULL")
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY due")]


# ---- task age tracking (Google Tasks has no creation timestamp) -----------

def note_task_seen(task_id: str):
    """No-op if already recorded — first_seen is set once and never moves."""
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO task_seen (task_id, first_seen) VALUES (?, date('now'))",
                 (task_id,))


def task_first_seen(task_ids: list[str]) -> dict[str, str]:
    if not task_ids:
        return {}
    with conn() as c:
        q = f"SELECT task_id, first_seen FROM task_seen WHERE task_id IN ({','.join('?' * len(task_ids))})"
        return {r["task_id"]: r["first_seen"] for r in c.execute(q, task_ids)}


def forget_tasks_not_in(task_ids: list[str]):
    """Drop age-tracking rows for tasks that no longer exist (completed and
    cleared, or deleted), so the table doesn't grow forever."""
    with conn() as c:
        if task_ids:
            q = f"DELETE FROM task_seen WHERE task_id NOT IN ({','.join('?' * len(task_ids))})"
            c.execute(q, task_ids)
        else:
            c.execute("DELETE FROM task_seen")


# ---- weight check-in --------------------------------------------------

def log_weight(weight_lb: float, note: str = "", d: date | None = None):
    with conn() as c:
        c.execute("INSERT INTO weight_logs (date, weight_lb, note) VALUES (?,?,?) "
                 "ON CONFLICT(date) DO UPDATE SET weight_lb=excluded.weight_lb, note=excluded.note",
                 ((d or date.today()).isoformat(), weight_lb, note))


def weight_logs(since: date, limit: int = 8):
    with conn() as c:
        rows = c.execute("SELECT * FROM weight_logs WHERE date>=? ORDER BY date DESC LIMIT ?",
                         (since.isoformat(), limit))
        return list(reversed([dict(r) for r in rows]))


# ---- strength quick-add -----------------------------------------------

def log_strength(exercise: str, sets: int | None = None, reps: int | None = None,
                 weight_lb: float | None = None, note: str = "", d: date | None = None) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO strength_logs (date, exercise, sets, reps, weight_lb, note) "
                        "VALUES (?,?,?,?,?,?)",
                        ((d or date.today()).isoformat(), exercise, sets, reps, weight_lb, note))
        return cur.lastrowid


def strength_logs(since: date):
    with conn() as c:
        rows = c.execute("SELECT * FROM strength_logs WHERE date>=? ORDER BY date DESC",
                         (since.isoformat(),))
        return [dict(r) for r in rows]


# ---- push subscriptions ----------------------------------------------------

def add_push_subscription(endpoint: str, p256dh: str, auth: str):
    with conn() as c:
        c.execute("INSERT INTO push_subscriptions (endpoint, p256dh, auth) VALUES (?,?,?) "
                 "ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth",
                 (endpoint, p256dh, auth))


def remove_push_subscription(endpoint: str):
    with conn() as c:
        c.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))


def list_push_subscriptions():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM push_subscriptions")]
