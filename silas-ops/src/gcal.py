"""Google Calendar, read only.

Auth is shared across Calendar/Tasks/Drive — see google_auth.py for the one
OAuth flow that grants all three scopes at once. This module just asks
google_auth for credentials and builds the Calendar client on top.

If anything about auth fails, the dashboard still renders using the static
anchors in term.yaml and shows a stale-data banner. That is deliberate. A
dashboard that refuses to open when the network is down is a dashboard you
stop opening.
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import google_auth

TZ = ZoneInfo("America/Toronto")
CACHE = Path("data/.calendar_cache.json")


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    location: str = ""
    calendar: str = ""

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)

    def to_dict(self):
        return {"title": self.title, "start": self.start.isoformat(),
                "end": self.end.isoformat(), "all_day": self.all_day,
                "location": self.location, "calendar": self.calendar}

    @staticmethod
    def from_dict(d):
        return Event(d["title"], datetime.fromisoformat(d["start"]),
                     datetime.fromisoformat(d["end"]), d.get("all_day", False),
                     d.get("location", ""), d.get("calendar", ""))


def _service():
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=google_auth.credentials(),
                 cache_discovery=False)


def fetch(days: int = 14, calendars: list[str] | None = None) -> tuple[list[Event], bool]:
    """Returns (events, live). live=False means the cache was used."""
    try:
        svc = _service()
        cal_ids = calendars or [c["id"] for c in
                                svc.calendarList().list().execute().get("items", [])
                                if c.get("selected", True)]
        lo = datetime.combine(date.today(), time.min, TZ)
        hi = lo + timedelta(days=days)
        out: list[Event] = []
        for cid in cal_ids:
            res = svc.events().list(calendarId=cid, timeMin=lo.isoformat(),
                                    timeMax=hi.isoformat(), singleEvents=True,
                                    orderBy="startTime", maxResults=250).execute()
            for e in res.get("items", []):
                s, en = e["start"], e["end"]
                if "date" in s:
                    st = datetime.combine(date.fromisoformat(s["date"]), time.min, TZ)
                    et = datetime.combine(date.fromisoformat(en["date"]), time.min, TZ)
                    out.append(Event(e.get("summary", "(no title)"), st, et, True,
                                     e.get("location", ""), cid))
                else:
                    out.append(Event(
                        e.get("summary", "(no title)"),
                        datetime.fromisoformat(s["dateTime"]).astimezone(TZ),
                        datetime.fromisoformat(en["dateTime"]).astimezone(TZ),
                        False, e.get("location", ""), cid))
        out.sort(key=lambda x: x.start)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"fetched": datetime.now(TZ).isoformat(),
                                     "events": [e.to_dict() for e in out]}))
        return out, True
    except Exception:
        if CACHE.exists():
            d = json.loads(CACHE.read_text())
            return [Event.from_dict(x) for x in d["events"]], False
        return [], False


def on_day(events: list[Event], d: date) -> list[Event]:
    return [e for e in events if e.start.date() <= d <= (e.end.date() if e.all_day
            else e.end.date()) and (e.all_day or e.start.date() == d)]


def gaps(events: list[Event], d: date, wake: str = "06:00",
         sleep: str = "22:30", min_minutes: int = 25) -> list[tuple[datetime, datetime]]:
    """Usable windows between committed blocks. This is the number that matters,
    not the event list. Energy is the constraint, and gaps are where it goes."""
    lo = datetime.combine(d, time.fromisoformat(wake), TZ)
    hi = datetime.combine(d, time.fromisoformat(sleep), TZ)
    blocks = sorted([(max(e.start, lo), min(e.end, hi))
                     for e in on_day(events, d) if not e.all_day
                     and e.end > lo and e.start < hi])
    merged: list[list[datetime]] = []
    for s, e in blocks:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, cur = [], lo
    for s, e in merged:
        if (s - cur).total_seconds() / 60 >= min_minutes:
            out.append((cur, s))
        cur = max(cur, e)
    if (hi - cur).total_seconds() / 60 >= min_minutes:
        out.append((cur, hi))
    return out
