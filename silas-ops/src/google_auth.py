"""Shared Google OAuth, used by gcal.py, gtasks.py, and drive.py.

One authorization, one token, three scopes. The user grants Calendar
(read-only), Tasks (read/write), and Drive-file (files this app creates
only) in a single consent screen instead of three separate ones.

Two ways to mint the token:
  - Web flow, for the deployed app: visit /oauth/google/start on the phone
    or any browser, approve, land back on /oauth/google/callback. This is
    the one that matters once this is running on Render, since there is no
    local browser on the server to pop open.
  - Desktop flow (`python -m src.cli auth`), for local development: opens
    a browser on your own machine. Produces a token in the same format, at
    the same path, so either path is interchangeable.

Both write secrets/token.json in the same authorized-user JSON shape, so
gcal.py / gtasks.py / drive.py only ever need to call credentials() here
and never touch OAuth mechanics themselves.
"""

from __future__ import annotations
import json
from pathlib import Path

SECRETS = Path("secrets")
CREDS = SECRETS / "credentials.json"
TOKEN = SECRETS / "token.json"

ALL_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.file",
]


class NotAuthorized(Exception):
    """No valid token yet. Caller should fall back to cache or show a
    'connect Google' prompt instead of hard-failing the page."""


def credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not TOKEN.exists():
        raise NotAuthorized("no token yet — visit /oauth/google/start")
    creds = Credentials.from_authorized_user_file(str(TOKEN), ALL_SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
        return creds
    raise NotAuthorized("token invalid and not refreshable — re-run auth")


def is_authorized() -> bool:
    try:
        credentials()
        return True
    except Exception:
        return False


def web_flow(redirect_uri: str):
    """Flow object for the /oauth/google/start -> /oauth/google/callback
    round trip. Caller stashes flow.state in the session to check on
    callback (CSRF protection for the OAuth dance)."""
    from google_auth_oauthlib.flow import Flow

    if not CREDS.exists():
        raise FileNotFoundError(
            "secrets/credentials.json missing. Google Cloud Console -> "
            "OAuth client ID -> Web application -> add this redirect URI -> "
            "download JSON -> save as secrets/credentials.json")
    return Flow.from_client_secrets_file(
        str(CREDS), scopes=ALL_SCOPES, redirect_uri=redirect_uri)


def save_credentials(creds):
    SECRETS.mkdir(exist_ok=True)
    TOKEN.write_text(creds.to_json())


DESKTOP_AUTH_PORT = 8765  # fixed, not random — see setup note below


def desktop_flow():
    """Local-machine auth for `python -m src.cli auth`. Not used by the
    deployed server — there's no browser to open there.

    Uses a fixed port rather than run_local_server's default random one
    because the OAuth client below is registered as "Web application" (so
    the same credentials.json also works for the deployed web flow), and
    Web application clients require every redirect URI to be pre-registered
    exactly — a random port can't be. Register
    http://localhost:8765/ alongside the Render callback URL in Google
    Cloud Console's "Authorized redirect URIs" and this matches every time.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDS.exists():
        raise FileNotFoundError("secrets/credentials.json missing")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), ALL_SCOPES)
    creds = flow.run_local_server(port=DESKTOP_AUTH_PORT)
    save_credentials(creds)
    return creds
