"""Journal: the 3 fixed prompts plus 1 rotating prompt drawn via a
shuffle-bag (shuffle the whole active pool once, hand prompts out in that
order with no repeats, reshuffle once exhausted). Today's draw is cached
in settings so reloading the page mid-day doesn't silently swap prompts
out from under a half-written entry.

Each day's entry saves to <DATA_DIR>/journal/YYYY-MM-DD.md and mirrors to
Drive via drive.py (drive.file scope — the app can only ever see files it
created). Nothing here ever reads that file back for anything but the
save/sync path itself — see the privacy note in db.py and the build spec.

DATA_DIR defaults to "data" locally (so this is data/journal/ in local
dev — same root db.py's ops.db lives under) but on Render points at the
mounted persistent disk, same as db.py — see render.yaml's `disk` block.
Without it, journal entries would sit on Render's default ephemeral
filesystem and get wiped on every redeploy.
"""

from __future__ import annotations
import json
import os
import random
from datetime import date
from pathlib import Path

from . import db, drive

JOURNAL_DIR = Path(os.environ.get("DATA_DIR", "data")) / "journal"


def todays_rotating_prompt() -> dict | None:
    today = date.today().isoformat()
    active = db.list_prompts("rotating")
    if not active:
        return None
    active_ids = {p["id"] for p in active}
    by_id = {p["id"]: p for p in active}

    cached = json.loads(db.get_setting("rotating_today") or "null")
    if cached and cached.get("date") == today and cached.get("prompt_id") in active_ids:
        return by_id[cached["prompt_id"]]

    bag = [pid for pid in json.loads(db.get_setting("rotating_bag") or "[]") if pid in active_ids]
    if not bag:
        bag = list(active_ids)
        random.shuffle(bag)

    prompt_id = bag.pop(0)
    db.set_setting("rotating_bag", json.dumps(bag))
    db.set_setting("rotating_today", json.dumps({"date": today, "prompt_id": prompt_id}))
    return by_id[prompt_id]


def todays_prompts() -> list[dict]:
    fixed = db.list_prompts("fixed")
    rotating = todays_rotating_prompt()
    return fixed + ([rotating] if rotating else [])


def _entry_path(d: date) -> Path:
    return JOURNAL_DIR / f"{d.isoformat()}.md"


def save_entry(responses: dict[int, str], d: date | None = None):
    """responses: {prompt_id: text}. Saves each answered prompt to the DB
    (so the reflect view and future re-renders can find it) and writes the
    day's full file, then mirrors that file to Drive."""
    d = d or date.today()
    prompts = {p["id"]: p for p in db.list_prompts(include_archived=True)}
    answered = {pid: text.strip() for pid, text in responses.items()
               if text.strip() and pid in prompts}
    for prompt_id, text in answered.items():
        db.save_journal_response(prompt_id, text, d)

    lines = [f"# {d.isoformat()}", ""]
    for prompt_id, text in answered.items():
        lines.append(f"## {prompts[prompt_id]['text']}")
        lines.append("")
        lines.append(text)
        lines.append("")

    JOURNAL_DIR.mkdir(exist_ok=True)
    path = _entry_path(d)
    path.write_text("\n".join(lines), encoding="utf-8")
    drive.sync_file(path)
    return path
