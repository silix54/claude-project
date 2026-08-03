"""Weekly safety-net backup: live DB (Turso in production) -> a local
.db file -> the same Google Drive folder journal entries already sync
to. Not user-facing — no page, no nav entry, nothing to configure from
the phone.

Why this needs an external trigger instead of an in-process scheduler:
Render's free plan spins the app down after ~15 minutes with no HTTP
traffic and only wakes it on the next request. A background thread
started at app boot would simply not be running most of the time, so it
can't be trusted to fire on a weekly clock. Instead, GitHub Actions
(free, runs independently of whether Render is awake) hits
POST /internal/backup on a weekly cron — see
.github/workflows/weekly-backup.yml — which both wakes the app and
triggers the backup in one request, using the same live Google token
the deployed app already refreshes for journal syncing.
"""

from __future__ import annotations
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from . import db, drive

BACKUP_KEEP = 6
FILENAME_PREFIX = "ops-backup-"


def dump_to_file(dest: Path) -> None:
    """Read every table's schema + rows straight off the live connection
    (Turso in production, local sqlite in dev — db.conn() already picks
    whichever one is active) and reproduce them in a brand-new local
    sqlite3 file. Schema comes from sqlite_master itself rather than
    db.SCHEMA, so the backup always matches what the live database
    actually has, migrations included, instead of what the code
    currently thinks it should have."""
    if dest.exists():
        dest.unlink()
    with db.conn() as c:
        # sqlite_sequence is an internal bookkeeping table SQLite creates
        # and manages itself for AUTOINCREMENT columns — it already gets
        # (re)created as a side effect of creating the other tables, and
        # naming it explicitly in a CREATE TABLE is a reserved-name error.
        tables = [(r["name"], r["sql"]) for r in c.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' "
            "AND sql IS NOT NULL AND name != 'sqlite_sequence'")]

        out = sqlite3.connect(dest)
        try:
            for name, create_sql in tables:
                out.execute(create_sql)
                cols = [r["name"] for r in c.execute(f"PRAGMA table_info({name})")]
                col_list = ",".join(cols)
                rows = [tuple(r[col] for col in cols)
                       for r in c.execute(f"SELECT {col_list} FROM {name}")]
                if rows:
                    out.executemany(
                        f"INSERT INTO {name} ({col_list}) VALUES ({','.join('?' * len(cols))})",
                        rows)
            out.commit()
        finally:
            out.close()


def run() -> dict:
    """Called by POST /internal/backup and `python -m src.cli backup`.
    Returns a status dict instead of raising, so the route can report a
    clean JSON error instead of a bare 500."""
    filename = f"{FILENAME_PREFIX}{date.today().isoformat()}.db"
    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / filename
        try:
            dump_to_file(local_path)
        except Exception as e:
            return {"ok": False, "step": "dump", "error": str(e)}
        try:
            drive.upload_backup(local_path, keep=BACKUP_KEEP)
        except Exception as e:
            return {"ok": False, "step": "upload", "error": str(e)}
    return {"ok": True, "file": filename}
