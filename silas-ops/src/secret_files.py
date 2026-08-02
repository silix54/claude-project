"""Where secret files actually live, across two different environments.

Locally (laptop dev, `cli auth`, `cli push-keys`), everything sits under
secrets/<name> in the project directory, exactly where this app writes it.

On Render, the "Secret Files" feature doesn't support subdirectories —
whatever path you type in its "path" field, the file is mounted flat at
/etc/secrets/<basename>, read-only. So secrets/credentials.json uploaded
there lands at /etc/secrets/credentials.json, not secrets/credentials.json.

read_path() checks both and returns whichever exists (local first, so a
laptop checkout with a real secrets/ directory always wins over a stray
/etc/secrets mount). write_path() always returns the local path — this app
only ever writes files it generates itself (OAuth tokens), and /etc/secrets
is read-only on Render, so there's nowhere else a write could go.
"""

from __future__ import annotations
from pathlib import Path

LOCAL_DIR = Path("secrets")
RENDER_DIR = Path("/etc/secrets")


def read_path(name: str) -> Path:
    """The path to check/open for reading. Falls back to the local path
    (which then reports not-existing) if neither location has the file —
    callers already handle a missing file via .exists() or a caught
    FileNotFoundError, so this never needs to raise itself."""
    local = LOCAL_DIR / name
    if local.exists():
        return local
    render = RENDER_DIR / name
    if render.exists():
        return render
    return local


def exists(name: str) -> bool:
    return (LOCAL_DIR / name).exists() or (RENDER_DIR / name).exists()


def write_path(name: str) -> Path:
    LOCAL_DIR.mkdir(exist_ok=True)
    return LOCAL_DIR / name
