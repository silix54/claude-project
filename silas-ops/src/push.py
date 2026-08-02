"""Web Push. VAPID keypair identifies this server to push services (no
third-party push provider, no account beyond the key pair itself).
Reminders covered: devotions not logged by evening, today's overdue/due
tasks each morning, deadlines inside 48 hours. A background thread checks
these on an interval and sends at most once per day per reminder kind, so
a container restart or a slow check loop doesn't spam duplicates.
"""

from __future__ import annotations
import json
import threading
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VAPID_FILE = Path("secrets/vapid.json")            # {public_key, subject}
VAPID_PRIVATE_PEM = Path("secrets/vapid_private.pem")
TZ = ZoneInfo("America/Toronto")
CHECK_INTERVAL_SECONDS = 900  # 15 min: reminders are daily-grain, not urgent


def generate_vapid_keys(subject: str = "mailto:you@example.com"):
    """The browser's applicationServerKey wants the raw, uncompressed EC
    point, base64url-encoded — not the PEM py_vapid saves by default. Keep
    both: PEM for pywebpush's signing, the raw-point encoding for the
    client's PushManager.subscribe() call."""
    from py_vapid import Vapid02
    from cryptography.hazmat.primitives import serialization
    import base64

    v = Vapid02()
    v.generate_keys()
    raw = v.public_key.public_bytes(serialization.Encoding.X962,
                                    serialization.PublicFormat.UncompressedPoint)
    pub_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    VAPID_FILE.parent.mkdir(exist_ok=True)
    VAPID_PRIVATE_PEM.write_text(v.private_pem().decode())
    VAPID_FILE.write_text(json.dumps({"public_key": pub_b64, "subject": subject}))
    return v


def public_key() -> str | None:
    if not VAPID_FILE.exists():
        return None
    return json.loads(VAPID_FILE.read_text())["public_key"]


def _vapid_claims():
    cfg = json.loads(VAPID_FILE.read_text())
    return {"sub": cfg["subject"]}


def send(subscription: dict, payload: dict) -> bool:
    from pywebpush import webpush, WebPushException

    if not VAPID_FILE.exists() or not VAPID_PRIVATE_PEM.exists():
        return False
    try:
        webpush(subscription_info=subscription, data=json.dumps(payload),
               vapid_private_key=str(VAPID_PRIVATE_PEM), vapid_claims=_vapid_claims())
        return True
    except WebPushException:
        return False  # includes 404/410 (dead subscription) — caller prunes either way


def broadcast(payload: dict):
    from . import db

    for row in db.list_push_subscriptions():
        sub = {"endpoint": row["endpoint"],
               "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}}
        ok = send(sub, payload)
        if not ok:
            db.remove_push_subscription(row["endpoint"])


def _sent_today(kind: str) -> bool:
    from . import db
    return db.get_setting(f"push_sent_{kind}") == date.today().isoformat()


def _mark_sent(kind: str):
    from . import db
    db.set_setting(f"push_sent_{kind}", date.today().isoformat())


def check_and_send():
    """One pass of the reminder checks. Safe to call repeatedly — each
    reminder kind is gated to fire once per calendar day."""
    from . import db, gtasks
    now = datetime.now(TZ)
    today = date.today()

    if now.hour >= 20 and not _sent_today("devotions"):
        if not db.devotions_logs(today):
            broadcast({"title": "Devotions", "body": "Not logged yet today."})
        _mark_sent("devotions")

    if 6 <= now.hour < 9 and not _sent_today("tasks"):
        tasks = gtasks.load()
        due = [t for t in gtasks.open_tasks(tasks) if t.overdue or t.due_today]
        if due:
            broadcast({"title": "Today's tasks",
                      "body": f"{len(due)} due or overdue: {due[0].text}" +
                              (f" +{len(due)-1} more" if len(due) > 1 else "")})
        _mark_sent("tasks")

    if not _sent_today("deadlines"):
        from .assemble import deadline_pressure
        soon = [d for d in deadline_pressure(horizon_days=2) if 0 <= d["days"] <= 2]
        if soon:
            broadcast({"title": "Deadline inside 48h",
                      "body": f"{soon[0]['course']} — {soon[0]['title']} in {soon[0]['days']}d"})
        _mark_sent("deadlines")


def start_background_loop(app):
    """Runs inside the Flask process. Fine for a single-user Render free
    instance; the instance is awake at most a couple times a day anyway,
    so this only meaningfully runs while someone's actually using it."""
    def loop():
        while True:
            try:
                with app.app_context():
                    check_and_send()
            except Exception:
                pass
            time.sleep(CHECK_INTERVAL_SECONDS)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
