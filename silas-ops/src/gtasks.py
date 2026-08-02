"""Google Tasks, read/write. This is the task backend for the whole app —
data/TASKS.md and src/tasks.py are dead once this is wired in; kept only
as a reference for the @tag !quadrant ~estimate parsing convention, which
this module reuses on the Google Tasks `notes` field instead.

One correction to the original spec: Google Tasks tasks do not carry a
creation timestamp. The API only exposes `updated`, `due`, and `completed`
(https://developers.google.com/tasks/reference/rest/v1/tasks). "Stalled
7+ days" therefore can't be read off the API directly — db.py stamps the
date we first see each task id (task_seen table) and that's what age
tracking uses here. It's the age-tracking build the spec said to skip, but
only because the field it was counting on doesn't exist.

Mirrors src/tasks.py's Task interface (same field names: text, done, tag,
quadrant, est_minutes, due, plus .overdue/.due_today/.sort_key) so render.py
and assemble.py need no changes to consume it.
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import db, google_auth

CACHE = Path("data/.tasks_cache.json")

QUADRANTS = {"now": "Do now", "plan": "Schedule", "quick": "Delegate or batch",
             "drop": "Drop"}
RANK = {"now": 0, "plan": 1, "quick": 2, "drop": 3, None: 4}

TAG = re.compile(r"@(\w+)")
QUAD = re.compile(r"!(now|plan|quick|drop)\b")
EST = re.compile(r"~(\d+)(m|h)\b")


@dataclass
class GTask:
    id: str
    text: str
    done: bool = False
    tag: str | None = None
    quadrant: str | None = None
    est_minutes: int | None = None
    due: date | None = None
    notes_raw: str = ""
    first_seen: str | None = None
    completed_at: date | None = None

    @property
    def overdue(self) -> bool:
        return bool(self.due and not self.done and self.due < date.today())

    @property
    def due_today(self) -> bool:
        return bool(self.due and not self.done and self.due == date.today())

    @property
    def stalled(self) -> bool:
        """Open 7+ days by our own first-seen stamp, not the API's `updated`
        (which changes on every edit, not just creation)."""
        if self.done or not self.first_seen:
            return False
        return (date.today() - date.fromisoformat(self.first_seen)).days >= 7

    def sort_key(self):
        return (RANK[self.quadrant], self.due or date.max)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "done": self.done, "tag": self.tag,
                "quadrant": self.quadrant, "est_minutes": self.est_minutes,
                "due": self.due.isoformat() if self.due else None,
                "notes_raw": self.notes_raw, "first_seen": self.first_seen,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None}

    @staticmethod
    def from_dict(d):
        return GTask(d["id"], d["text"], d["done"], d.get("tag"), d.get("quadrant"),
                    d.get("est_minutes"), date.fromisoformat(d["due"]) if d.get("due") else None,
                    d.get("notes_raw", ""), d.get("first_seen"),
                    date.fromisoformat(d["completed_at"]) if d.get("completed_at") else None)


def parse_notes(notes: str) -> tuple[str | None, str | None, int | None]:
    """(tag, quadrant, est_minutes) parsed out of the notes field. Unlike the
    flat-file convention, `due:` isn't parsed here — Google Tasks has a real
    due-date field for that."""
    tag = q = est = None
    if (m := TAG.search(notes)):
        tag = m.group(1)
    if (m := QUAD.search(notes)):
        q = m.group(1)
    if (m := EST.search(notes)):
        n = int(m.group(1))
        est = n * 60 if m.group(2) == "h" else n
    return tag, q, est


def _service():
    from googleapiclient.discovery import build
    return build("tasks", "v1", credentials=google_auth.credentials(), cache_discovery=False)


def _to_gtask(item: dict) -> GTask:
    notes = item.get("notes", "") or ""
    tag, q, est = parse_notes(notes)
    due = None
    if item.get("due"):
        due = datetime.fromisoformat(item["due"].replace("Z", "+00:00")).date()
    completed_at = None
    if item.get("completed"):
        completed_at = datetime.fromisoformat(item["completed"].replace("Z", "+00:00")).date()
    return GTask(id=item["id"], text=item.get("title", ""),
                done=item.get("status") == "completed", tag=tag, quadrant=q,
                est_minutes=est, due=due, notes_raw=notes, completed_at=completed_at)


def fetch(tasklist: str = "@default") -> tuple[list[GTask], bool]:
    """Returns (tasks, live). live=False means the cache was used — same
    never-hard-fail contract as gcal.fetch()."""
    try:
        svc = _service()
        out: list[GTask] = []
        page_token = None
        while True:
            res = svc.tasks().list(tasklist=tasklist, showCompleted=True,
                                   showHidden=True, maxResults=100,
                                   pageToken=page_token).execute()
            out.extend(_to_gtask(item) for item in res.get("items", []))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        ids = [t.id for t in out]
        for tid in ids:
            db.note_task_seen(tid)
        db.forget_tasks_not_in(ids)
        seen = db.task_first_seen(ids)
        for t in out:
            t.first_seen = seen.get(t.id)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps([t.to_dict() for t in out]))
        return out, True
    except Exception:
        if CACHE.exists():
            out = [GTask.from_dict(d) for d in json.loads(CACHE.read_text())]
            seen = db.task_first_seen([t.id for t in out])
            for t in out:
                t.first_seen = seen.get(t.id)
            return out, False
        return [], False


def load(tasklist: str = "@default") -> list[GTask]:
    tasks, _ = fetch(tasklist)
    return tasks


def open_tasks(tasks: list[GTask]) -> list[GTask]:
    return sorted([t for t in tasks if not t.done], key=GTask.sort_key)


def today_slate(tasks: list[GTask], limit: int = 5) -> list[GTask]:
    o = open_tasks(tasks)
    pinned = [t for t in o if t.overdue or t.due_today]
    rest = [t for t in o if t not in pinned]
    return (pinned + rest)[:limit]


def stalled_tasks(tasks: list[GTask]) -> list[GTask]:
    return [t for t in open_tasks(tasks) if t.stalled]


def completed_since(tasks: list[GTask], since: date) -> list[GTask]:
    return [t for t in tasks if t.done and t.completed_at and t.completed_at >= since]


def committed_minutes(tasks: list[GTask]) -> int:
    return sum(t.est_minutes or 0 for t in today_slate(tasks))


def _notes_for(tag: str | None, quadrant: str | None, est_minutes: int | None) -> str:
    parts = []
    if tag:
        parts.append(f"@{tag}")
    if quadrant:
        parts.append(f"!{quadrant}")
    if est_minutes:
        parts.append(f"~{est_minutes}m" if est_minutes < 60 and est_minutes % 60
                     else f"~{est_minutes // 60}h")
    return " ".join(parts)


def create_task(title: str, tag: str | None = None, quadrant: str | None = None,
                est_minutes: int | None = None, due: date | None = None,
                tasklist: str = "@default") -> str:
    body = {"title": title, "notes": _notes_for(tag, quadrant, est_minutes)}
    if due:
        body["due"] = datetime.combine(due, datetime.min.time()).isoformat() + "Z"
    item = _service().tasks().insert(tasklist=tasklist, body=body).execute()
    db.note_task_seen(item["id"])
    return item["id"]


def complete_task(task_id: str, tasklist: str = "@default"):
    _service().tasks().patch(tasklist=tasklist, task=task_id,
                             body={"status": "completed"}).execute()


def set_due(task_id: str, due: date | None, tasklist: str = "@default"):
    body = {"due": (datetime.combine(due, datetime.min.time()).isoformat() + "Z") if due else None}
    _service().tasks().patch(tasklist=tasklist, task=task_id, body=body).execute()


def push_due_by_days(task_id: str, current_due: date | None, days: int = 7,
                     tasklist: str = "@default"):
    base = current_due or date.today()
    from datetime import timedelta
    set_due(task_id, base + timedelta(days=days), tasklist=tasklist)


def patch_meta(task_id: str, tag: str | None, quadrant: str | None, est_minutes: int | None,
               tasklist: str = "@default"):
    """Rewrite the @tag !quadrant ~estimate notes convention wholesale —
    used by triage's drop action (quadrant -> drop) and the quick-add form."""
    _service().tasks().patch(tasklist=tasklist, task=task_id,
                             body={"notes": _notes_for(tag, quadrant, est_minutes)}).execute()


def delete_task(task_id: str, tasklist: str = "@default"):
    _service().tasks().delete(tasklist=tasklist, task=task_id).execute()
