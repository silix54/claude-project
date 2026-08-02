"""Parse TASKS.md.

Format is deliberately plain so you can edit it in any editor, on any device,
and diff it in git.

    - [ ] Confirm DND hiring mechanism @career !now ~30m due:2026-08-08
    - [x] Submit BUSI 4301 proposal @school

  @tag     one context tag: school work career faith fitness admin
  !now     Eisenhower quadrant: !now (urgent+important), !plan (important),
           !quick (urgent only), !drop (neither)
  ~30m     time estimate, m or h
  due:     ISO date
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

QUADRANTS = {"now": "Do now", "plan": "Schedule", "quick": "Delegate or batch",
             "drop": "Drop"}
RANK = {"now": 0, "plan": 1, "quick": 2, "drop": 3, None: 4}


@dataclass
class Task:
    text: str
    done: bool = False
    tag: str | None = None
    quadrant: str | None = None
    est_minutes: int | None = None
    due: date | None = None
    raw: str = ""

    @property
    def overdue(self) -> bool:
        return bool(self.due and not self.done and self.due < date.today())

    @property
    def due_today(self) -> bool:
        return bool(self.due and not self.done and self.due == date.today())

    def sort_key(self):
        return (RANK[self.quadrant], self.due or date.max)


LINE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.+?)\s*$")
TAG = re.compile(r"@(\w+)")
QUAD = re.compile(r"!(now|plan|quick|drop)\b")
EST = re.compile(r"~(\d+)(m|h)\b")
DUE = re.compile(r"due:(\d{4}-\d{2}-\d{2})")


def parse_line(line: str) -> Task | None:
    m = LINE.match(line)
    if not m:
        return None
    done = m.group(1).lower() == "x"
    body = m.group(2)
    raw = body

    tag = q = None
    est = due = None

    if (t := TAG.search(body)):
        tag = t.group(1)
    if (t := QUAD.search(body)):
        q = t.group(1)
    if (t := EST.search(body)):
        n = int(t.group(1))
        est = n * 60 if t.group(2) == "h" else n
    if (t := DUE.search(body)):
        due = date.fromisoformat(t.group(1))

    text = DUE.sub("", QUAD.sub("", EST.sub("", TAG.sub("", body)))).strip()
    text = re.sub(r"\s{2,}", " ", text)
    return Task(text, done, tag, q, est, due, raw)


def load(path: str | Path) -> list[Task]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if (t := parse_line(line)):
            out.append(t)
    return out


def open_tasks(tasks: list[Task]) -> list[Task]:
    return sorted([t for t in tasks if not t.done], key=Task.sort_key)


def today_slate(tasks: list[Task], limit: int = 5) -> list[Task]:
    """What actually gets attention today. Overdue and due-today first, then
    the highest-quadrant open work, capped so the list stays honest."""
    o = open_tasks(tasks)
    pinned = [t for t in o if t.overdue or t.due_today]
    rest = [t for t in o if t not in pinned]
    return (pinned + rest)[:limit]


def committed_minutes(tasks: list[Task]) -> int:
    return sum(t.est_minutes or 0 for t in today_slate(tasks))
