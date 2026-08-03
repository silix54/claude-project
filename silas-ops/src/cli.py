"""Command line entry, for local dev and one-off admin tasks. The deployed
app itself is served by app.py — this is for running things from a laptop:
minting the first OAuth token, generating push keys, previewing the
dashboard without opening the web app.

  python -m src.cli today       render + open the dashboard
  python -m src.cli state       dump the state as JSON
  python -m src.cli auth        run the Google OAuth flow once (desktop)
  python -m src.cli strava-auth print the URL to authorize Strava manually
  python -m src.cli push-keys   generate VAPID keys for web push
  python -m src.cli strength    log a strength set: exercise sets reps lb
  python -m src.cli weigh 148   log a weigh-in
  python -m src.cli check       config sanity check, no network
  python -m src.cli backup      run the weekly Turso->Drive backup now
"""

from __future__ import annotations
import json
import sys
import webbrowser
from pathlib import Path

from . import db
from .assemble import build
from .render import render

OUT = Path("out/dashboard.html")


def _json_default(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if hasattr(o, "__dict__"):
        return {k: v for k, v in vars(o).items() if not k.startswith("_")}
    return str(o)


def cmd_today(open_browser=True):
    s = build()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(s), encoding="utf-8")
    print(f"wrote {OUT}")
    if not s["calendar_live"]:
        print("warning: calendar not live, used cache")
    if not s["strava_live"]:
        print("warning: strava not live, used cache")
    if open_browser:
        webbrowser.open(OUT.resolve().as_uri())


def cmd_state():
    print(json.dumps(build(), default=_json_default, indent=2))


def cmd_auth():
    from . import google_auth
    google_auth.desktop_flow()
    print("authorised for Calendar + Tasks + Drive. token cached in secrets/token.json")


def cmd_strava_auth():
    print("Strava's OAuth needs a live redirect URI, so run this against the "
         "deployed app or `flask run` and visit /oauth/strava/start in a browser "
         "while logged in — there's no clean desktop flow for it the way Google has.")


def cmd_push_keys():
    from . import push
    subject = sys.argv[3] if len(sys.argv) > 3 else "mailto:you@example.com"
    push.generate_vapid_keys(subject)
    print(f"generated secrets/vapid.json + secrets/vapid_private.pem (subject={subject})")


def cmd_strength(argv):
    if not argv:
        print("usage: strength <exercise> [sets] [reps] [weight_lb]")
        return
    db.log_strength(argv[0],
                    int(argv[1]) if len(argv) > 1 else None,
                    int(argv[2]) if len(argv) > 2 else None,
                    float(argv[3]) if len(argv) > 3 else None)
    print("logged", argv[0])


def cmd_weigh(argv):
    if not argv:
        print("usage: weigh <lb> [note...]")
        return
    db.log_weight(float(argv[0]), " ".join(argv[1:]))
    print("logged", argv[0], "lb")


def cmd_check():
    import yaml
    from . import secret_files
    ok = True
    for f in ["config/term.yaml", "config/training.yaml"]:
        try:
            yaml.safe_load(Path(f).read_text())
            print(f"ok   {f}")
        except Exception as e:
            ok = False
            print(f"FAIL {f}: {e}")
    for name, warning in [
        ("credentials.json", "calendar/tasks/drive will run offline"),
        ("token.json", "run `auth` (local) or /oauth/google/start (deployed)"),
        ("strava.json", "strava will run offline"),
        ("vapid.json", "push notifications disabled — run push-keys"),
    ]:
        if secret_files.exists(name):
            print(f"ok   {secret_files.read_path(name)}")
        else:
            print(f"warn {name} missing (checked secrets/ and /etc/secrets/) — {warning}")
    sys.exit(0 if ok else 1)


def cmd_backup():
    from . import backup
    result = backup.run()
    print(result)
    sys.exit(0 if result["ok"] else 1)


def main():
    db.init()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "today"
    rest = sys.argv[2:]
    {"today": lambda: cmd_today("--no-open" not in rest),
     "state": cmd_state,
     "auth": cmd_auth,
     "strava-auth": cmd_strava_auth,
     "push-keys": cmd_push_keys,
     "strength": lambda: cmd_strength(rest),
     "weigh": lambda: cmd_weigh(rest),
     "check": cmd_check,
     "backup": cmd_backup}.get(cmd, lambda: print(__doc__))()


if __name__ == "__main__":
    main()
