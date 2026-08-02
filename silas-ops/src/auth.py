"""Single shared password, session cookie. There's only ever one user, so
there are no accounts, no per-user rows anywhere, no password hashing
database — just one secret compared at login time and a signed session
cookie after that (Flask's default session is itself signed/tamper-proof
via SECRET_KEY, so this needs nothing extra on top).
"""

from __future__ import annotations
import hmac
import os
from functools import wraps

from flask import redirect, session, url_for


def check_password(candidate: str) -> bool:
    real = os.environ.get("APP_PASSWORD", "")
    if not real:
        raise RuntimeError("APP_PASSWORD env var is not set")
    return hmac.compare_digest(candidate, real)


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("authed"):
            return redirect(url_for("login", next=os_path()))
        return view(*a, **kw)
    return wrapped


def os_path():
    from flask import request
    return request.path
