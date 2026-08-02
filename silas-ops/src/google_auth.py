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

credentials.json is read-only from this app's side (you download it once
from Google Cloud Console), so it's looked up via secret_files.read_path()
— locally that's secrets/credentials.json, on Render it's whatever Secret
File you uploaded, which lands at /etc/secrets/credentials.json regardless
of the path you typed for it (see secret_files.py). token.json is
different: this app writes it too (after the OAuth round trip, and on
every refresh), so writes always target the local secrets/ path — /etc/
secrets is a read-only mount on Render, there's nowhere else to write it.
"""

from __future__ import annotations

from . import secret_files

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

    token_path = secret_files.read_path("token.json")
    if not token_path.exists():
        raise NotAuthorized("no token yet — visit /oauth/google/start")
    creds = Credentials.from_authorized_user_file(str(token_path), ALL_SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        secret_files.write_path("token.json").write_text(creds.to_json())
        return creds
    raise NotAuthorized("token invalid and not refreshable — re-run auth")


def is_authorized() -> bool:
    try:
        credentials()
        return True
    except Exception:
        return False


def web_flow(redirect_uri: str, state: str | None = None):
    """Flow object for the /oauth/google/start -> /oauth/google/callback
    round trip.

    On /start, call with state=None — the Flow mints one (flow.state) and
    the caller stashes it in the session. On /callback, call with the
    session's stashed state passed back in: without it, the underlying
    oauthlib client's state-check is a silent no-op (it only compares when
    self.state is truthy), so the callback would accept a `state`/`code`
    pair from anywhere — an attacker's own OAuth flow, replayed onto a
    logged-in victim, would get their credentials saved as this app's. See
    the security-review finding this fixes.
    """
    from google_auth_oauthlib.flow import Flow

    creds_path = secret_files.read_path("credentials.json")
    if not creds_path.exists():
        raise FileNotFoundError(
            "credentials.json missing. Locally: save it to "
            "secrets/credentials.json. On Render: upload it as a Secret "
            "File (any path you type there — it lands flat at "
            "/etc/secrets/credentials.json). Google Cloud Console -> "
            "OAuth client ID -> Web application -> add this redirect URI -> "
            "download JSON.")
    return Flow.from_client_secrets_file(
        str(creds_path), scopes=ALL_SCOPES, redirect_uri=redirect_uri, state=state)


def save_credentials(creds):
    secret_files.write_path("token.json").write_text(creds.to_json())


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

    creds_path = secret_files.read_path("credentials.json")
    if not creds_path.exists():
        raise FileNotFoundError("secrets/credentials.json missing")
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), ALL_SCOPES)
    creds = flow.run_local_server(port=DESKTOP_AUTH_PORT)
    save_credentials(creds)
    return creds
