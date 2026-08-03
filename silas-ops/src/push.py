"""Web Push. VAPID keypair identifies this server to push services (no
third-party push provider, no account beyond the key pair itself).
Reminders covered: devotions not logged by evening, today's overdue/due
tasks each morning, deadlines inside 48 hours. check_and_send() gates each
reminder kind to at most once per calendar day, so calling it repeatedly
(or out of order) never spams duplicates.

check_and_send() is triggered externally via POST /internal/push-check
rather than an in-process scheduler — same reasoning as src/backup.py:
Render's free plan spins the app down after ~15 minutes idle, so a
background thread started at app boot only runs while someone happens to
be using the app, which defeats reminders whose whole point is to fire
when nobody's looking. See .github/workflows/push-check.yml.

Both key files (vapid.json, vapid_private.pem) are generated once, locally,
via `cli push-keys` — this app never regenerates them itself. Read-side,
they're looked up via secret_files.read_path(): locally that's
secrets/<name>, on Render it's whatever Secret File you uploaded (lands
flat at /etc/secrets/<name> regardless of the path typed for it).
"""

from __future__ import annotations
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import secret_files

TZ = ZoneInfo("America/Toronto")


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

    secret_files.write_path("vapid_private.pem").write_text(v.private_pem().decode())
    secret_files.write_path("vapid.json").write_text(json.dumps({"public_key": pub_b64,
                                                                   "subject": subject}))
    return v


def public_key() -> str | None:
    if not secret_files.exists("vapid.json"):
        return None
    return json.loads(secret_files.read_path("vapid.json").read_text())["public_key"]


def _vapid_claims():
    cfg = json.loads(secret_files.read_path("vapid.json").read_text())
    return {"sub": cfg["subject"]}


def send(subscription: dict, payload: dict) -> bool:
    from pywebpush import webpush, WebPushException

    if not secret_files.exists("vapid.json") or not secret_files.exists("vapid_private.pem"):
        return False
    try:
        webpush(subscription_info=subscription, data=json.dumps(payload),
               vapid_private_key=str(secret_files.read_path("vapid_private.pem")),
               vapid_claims=_vapid_claims())
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
