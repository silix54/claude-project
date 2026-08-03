"""Google Drive, `drive.file` scope only — the app can see and manage
exactly the files it creates itself, nothing else in the account. Used
only to mirror journal entries so they exist somewhere off the server too.

Shares OAuth with Calendar and Tasks via google_auth.py; no separate
consent screen.
"""

from __future__ import annotations
import json
from pathlib import Path

from . import google_auth

FOLDER_NAME = "Silas Ops Journal"
FOLDER_ID_CACHE = Path("data/.drive_folder_id.json")


def _service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=google_auth.credentials(), cache_discovery=False)


def _folder_id(svc) -> str:
    if FOLDER_ID_CACHE.exists():
        return json.loads(FOLDER_ID_CACHE.read_text())["id"]
    res = svc.files().list(
        q=f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces="drive", fields="files(id)").execute()
    files = res.get("files", [])
    if files:
        fid = files[0]["id"]
    else:
        meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
        fid = svc.files().create(body=meta, fields="id").execute()["id"]
    FOLDER_ID_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FOLDER_ID_CACHE.write_text(json.dumps({"id": fid}))
    return fid


def upload_backup(path: Path, keep: int = 6) -> None:
    """Uploads path as a brand-new file (never overwrites — each backup
    keeps its own dated name, unlike sync_file()'s update-by-name), then
    deletes the oldest ops-backup-* files beyond `keep` so the folder
    doesn't grow forever, but a bad week's dump still can't wipe out the
    last several good copies at once. Unlike sync_file(), this raises
    instead of swallowing errors — a backup that silently fails defeats
    the point of having a safety net, so the caller (backup.run()) needs
    to see it."""
    from googleapiclient.http import MediaFileUpload

    svc = _service()
    folder_id = _folder_id(svc)
    media = MediaFileUpload(str(path), mimetype="application/x-sqlite3")
    svc.files().create(body={"name": path.name, "parents": [folder_id]},
                       media_body=media, fields="id").execute()

    existing = svc.files().list(
        q=f"name contains 'ops-backup-' and '{folder_id}' in parents and trashed=false",
        spaces="drive", fields="files(id,name)", orderBy="name desc").execute().get("files", [])
    for f in existing[keep:]:
        svc.files().delete(fileId=f["id"]).execute()


def sync_file(path: Path) -> bool:
    """Best-effort mirror of a local file to the journal Drive folder.
    Returns False (never raises) if Google isn't connected — journaling
    should never fail just because the network or OAuth token is down;
    the local file already saved before this is called."""
    try:
        from googleapiclient.http import MediaFileUpload

        svc = _service()
        folder_id = _folder_id(svc)
        existing = svc.files().list(
            q=f"name='{path.name}' and '{folder_id}' in parents and trashed=false",
            spaces="drive", fields="files(id)").execute().get("files", [])
        media = MediaFileUpload(str(path), mimetype="text/markdown")
        if existing:
            svc.files().update(fileId=existing[0]["id"], media_body=media).execute()
        else:
            svc.files().create(body={"name": path.name, "parents": [folder_id]},
                               media_body=media, fields="id").execute()
        return True
    except Exception:
        return False
