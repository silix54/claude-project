"""Strava, read only. Covers all cardio training (run/bike/swim) — Garmin and
Google Health both already sync into Strava, so this is the one integration
that needs to exist; no separate Garmin client, and none should be built
(the unofficial Garmin API is a ToS gray area and unnecessary here).

Strava's OAuth is its own app (separate client id/secret from Google, kept
in secrets/strava.json), refreshed with a stored refresh token — not routed
through google_auth.py, since it's an unrelated provider.

Same never-hard-fail contract as gcal/gtasks: on any failure, fall back to
the last successful cache and let the caller show a stale indicator instead
of blanking the page.
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

SECRETS = Path("secrets")
CREDS = SECRETS / "strava.json"        # {client_id, client_secret}
TOKEN = SECRETS / "strava_token.json"  # {access_token, refresh_token, expires_at}
CACHE = Path("data/.strava_cache.json")

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API = "https://www.strava.com/api/v3"
SCOPE = "activity:read_all"

CARDIO_TYPES = {"Run", "Ride", "VirtualRide", "Swim", "TrailRun", "GravelRide"}


@dataclass
class Activity:
    id: int
    name: str
    type: str
    start: datetime
    minutes: int
    distance_km: float

    def to_dict(self):
        return {"id": self.id, "name": self.name, "type": self.type,
                "start": self.start.isoformat(), "minutes": self.minutes,
                "distance_km": self.distance_km}

    @staticmethod
    def from_dict(d):
        return Activity(d["id"], d["name"], d["type"], datetime.fromisoformat(d["start"]),
                        d["minutes"], d["distance_km"])


def is_connected() -> bool:
    return TOKEN.exists()


def authorize_url(redirect_uri: str) -> str:
    creds = json.loads(CREDS.read_text())
    return (f"{AUTH_URL}?client_id={creds['client_id']}&redirect_uri={redirect_uri}"
           f"&response_type=code&approval_prompt=auto&scope={SCOPE}")


def exchange_code(code: str):
    creds = json.loads(CREDS.read_text())
    r = requests.post(TOKEN_URL, data={
        "client_id": creds["client_id"], "client_secret": creds["client_secret"],
        "code": code, "grant_type": "authorization_code"}, timeout=10)
    r.raise_for_status()
    _save_token(r.json())


def _save_token(payload: dict):
    SECRETS.mkdir(exist_ok=True)
    TOKEN.write_text(json.dumps({
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": payload["expires_at"],
    }))


def _access_token() -> str:
    tok = json.loads(TOKEN.read_text())
    if tok["expires_at"] > time.time() + 60:
        return tok["access_token"]
    creds = json.loads(CREDS.read_text())
    r = requests.post(TOKEN_URL, data={
        "client_id": creds["client_id"], "client_secret": creds["client_secret"],
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=10)
    r.raise_for_status()
    payload = r.json()
    _save_token(payload)
    return payload["access_token"]


def fetch(days: int = 14) -> tuple[list[Activity], bool]:
    """Returns (activities, live). live=False means the cache was used."""
    try:
        if not TOKEN.exists():
            raise FileNotFoundError("Strava not connected yet")
        token = _access_token()
        after = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        r = requests.get(f"{API}/athlete/activities", params={"after": after, "per_page": 100},
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        out = []
        for a in r.json():
            out.append(Activity(
                id=a["id"], name=a.get("name", ""), type=a.get("type", ""),
                start=datetime.fromisoformat(a["start_date_local"].replace("Z", "+00:00")),
                minutes=round(a.get("moving_time", 0) / 60),
                distance_km=round(a.get("distance", 0) / 1000, 2)))
        out.sort(key=lambda x: x.start)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps([a.to_dict() for a in out]))
        return out, True
    except Exception:
        if CACHE.exists():
            return [Activity.from_dict(d) for d in json.loads(CACHE.read_text())], False
        return [], False


def cardio_dates(activities: list[Activity]) -> set[date]:
    return {a.start.date() for a in activities if a.type in CARDIO_TYPES}
