# silas-ops

A personal operations dashboard. No AI dependency anywhere in the core
system — everything here is deterministic Python (periodization math,
calendar/task reads, collision detection, habit/mood correlation). See
`BUILD_PROMPT.md` (kept alongside this repo, not inside it) for the full
design spec and philosophy.

## What's here

- `app.py` — Flask app: password gate, all routes for `/`, `/plan`,
  `/reflect`, `/settings`, OAuth (Google + Strava), push subscriptions.
- `src/periodization.py` — 3-on-1-deload cycle math, anchored to one date.
- `src/gcal.py` — Google Calendar read, offline cache fallback.
- `src/gtasks.py` — Google Tasks read/write, `@tag !quadrant ~estimate`
  parsing out of the notes field. Supersedes `src/tasks.py` (flat-file
  parser, kept only as a reference for the parsing convention — not wired
  into the app) and `data/TASKS.md` (same — a worked example, not read).
- `src/strava.py` — Strava OAuth, read-only, covers all cardio training.
- `src/drive.py` — Google Drive (`drive.file` scope only), mirrors journal
  entries.
- `src/google_auth.py` — the one shared OAuth flow for Calendar + Tasks +
  Drive (one consent screen, one token).
- `src/db.py` — SQLite layer: habits, mood/energy, journal, devotions,
  deadlines, strength/weight logs, settings, push subscriptions. Local
  file by default; talks to Turso (hosted libSQL) instead when
  `TURSO_DATABASE_URL` is set, so the data survives Render redeploys
  without needing a paid persistent disk — see `conn()`.
- `src/assemble.py` / `src/render.py` — daily view state + HTML.
- `src/assemble_plan.py` / `src/render_plan.py` — `/plan` (Sunday session).
- `src/assemble_reflect.py` / `src/render_reflect.py` — `/reflect`.
- `src/render_settings.py` — `/settings` CRUD forms.
- `src/journal.py` — shuffle-bag rotating prompt draw, entry save + Drive
  sync.
- `src/push.py` — Web Push (VAPID), reminder checks on a background loop.
- `config/term.yaml`, `config/training.yaml` — the two things that stay
  files, not database rows, because they change once a term.

## One correction to the original build spec

The spec assumed Google Tasks rows carry a native creation timestamp to
use for "stalled 7+ days" detection. They don't — the Tasks API v1 `Task`
resource only exposes `updated`, `due`, and `completed`
(https://developers.google.com/tasks/reference/rest/v1/tasks), not a
creation date. `src/gtasks.py` and `src/db.py` (`task_seen` table) work
around this by stamping the date each task id is first seen locally and
using that as the age anchor instead — the exact "custom age-tracking"
build the spec said to skip, but only because the field it assumed doesn't
exist.

## Setup

### 1. Python environment

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

### 2. Google Cloud (Calendar + Tasks + Drive)

One OAuth client covers all three:

1. console.cloud.google.com → new project → enable the Calendar API, Tasks
   API, and Drive API.
2. Credentials → Create credentials → OAuth client ID → **Web application**.
3. Authorized redirect URIs: add both
   - `https://<your-render-app>.onrender.com/oauth/google/callback`
     (once deployed)
   - `http://localhost:8765/` (for local `cli auth`; see
     `src/google_auth.py` for why the port is fixed, not random)
4. Download the JSON, save as `secrets/credentials.json`.
5. Locally: `python -m src.cli auth` (opens a browser once).
   Deployed: log into the app, visit `/oauth/google/start`.

### 3. Strava

1. strava.com/settings/api → create an app → note client ID/secret.
2. Save as `secrets/strava.json`: `{"client_id": "...", "client_secret": "..."}`
3. Authorization Callback Domain in the Strava app settings must match your
   Render domain (or `localhost` for local testing).
4. Log into the app, visit `/oauth/strava/start`.

### 4. Push notifications (optional)

    python -m src.cli push-keys "mailto:you@example.com"

Generates `secrets/vapid.json` + `secrets/vapid_private.pem`. The daily
view registers the service worker and subscribes automatically once these
exist.

### 5. Turso (optional locally, needed for persistence on Render)

Without this, `ops.db` is a local SQLite file that works fine for
development but gets wiped on every Render redeploy (Render's default
disk is ephemeral). Turso is a free hosted libSQL (SQLite-fork) database
that fixes that without needing a paid Render disk:

1. turso.tech → sign up → create a database.
2. Get its URL: `turso db show <db-name> --url` (or the dashboard) — looks
   like `libsql://<db-name>-<org>.turso.io`.
3. Get an auth token: `turso db tokens create <db-name>` (or the
   dashboard).
4. Set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` — locally in your shell
   if you want to develop against the real remote database, or just on
   Render (Settings → Environment, both marked `sync: false` in
   `render.yaml` so neither is ever in the repo). Leave both unset locally
   and `db.py` falls back to the local SQLite file, no Turso account
   needed for local dev.

`journal/` is **not** moved to Turso and stays on whatever local/ephemeral
disk the process has — that's intentional. `journal.save_entry()` already
mirrors every entry to Google Drive right after writing it locally (see
step 2's Drive scope), so Drive is the actual persistent copy; the local
file is disposable working storage that's fine to lose on redeploy.

### 6. Weekly Turso backup (safety net, no UI)

Turso's free tier has no built-in point-in-time backup, so once persistence
depends on it, a bad migration or an accidental `DELETE` has nothing to
undo it with. `src/backup.py` dumps the live database's full schema+data
to a local `.db` file and uploads it to the same "Silas Ops Journal" Drive
folder journal entries already sync to, keeping the last 6 weekly copies
(oldest deleted first) so one bad week doesn't overwrite the last good one.

It runs via `POST /internal/backup` (bearer-token gated, not a login
session) rather than an in-process scheduler, because Render's free plan
sleeps the app after ~15 minutes idle — a background thread only runs
while the process happens to be awake, which a personal 1-2x/day app can't
guarantee on a weekly clock. `.github/workflows/weekly-backup.yml` hits
that route every Sunday from GitHub Actions instead, which runs
independently of whether Render is awake and wakes it as a side effect.

One-time setup after deploying:
1. Render auto-generates `BACKUP_TOKEN` (see `render.yaml`) — copy its
   value from the Render dashboard (Environment tab).
2. In this repo's GitHub Settings → Secrets and variables → Actions, add:
   - `RENDER_APP_URL` — e.g. `https://silas-ops.onrender.com`
   - `BACKUP_TOKEN` — the value copied in step 1
3. To confirm it's actually working rather than trusting the cron: go to
   the Actions tab → "Weekly Turso backup" → "Run workflow" (the
   `workflow_dispatch` trigger runs it on demand), then check the "Silas
   Ops Journal" Drive folder for a new `ops-backup-<date>.db` file.

Can also be triggered from a shell with Google auth already set up
locally: `python -m src.cli backup`.

### 7. Push reminder checks (no UI)

Same reliability problem as the backup, for a different reason: the
reminders in `src/push.py` (devotions not logged by evening, tasks due
today each morning, deadlines inside 48h) are hour-gated — e.g. the tasks
reminder only fires between 6-9am — so they need the app awake *during
that window*, not just at some point in the day. An in-process scheduler
on Render's free plan can't promise that (the app sleeps after ~15 min
idle), so this uses the same external-trigger pattern as the backup:
`POST /internal/push-check` (bearer-token gated) runs `check_and_send()`,
which itself gates each reminder kind to at most once per calendar day so
an hourly cron never double-sends. `.github/workflows/push-check.yml`
hits that route every hour from GitHub Actions.

One-time setup after deploying:
1. Render auto-generates `PUSH_TOKEN` (see `render.yaml`) — copy its value
   from the Render dashboard (Environment tab).
2. In this repo's GitHub Settings → Secrets and variables → Actions, add
   `PUSH_TOKEN` (the value copied in step 1) — `RENDER_APP_URL` is likely
   already there from the backup workflow setup; reuse it.
3. To confirm it's working: Actions tab → "Push reminder check" → "Run
   workflow" (manual `workflow_dispatch` trigger), then check the response
   body in the run log — `{"ok": true}` means the checks ran (whether a
   notification actually sent depends on the time of day and whether
   there's anything to remind about).

### 8. Environment variables

- `APP_PASSWORD` — required. The single shared password.
- `FLASK_SECRET_KEY` — recommended in production (Render's `render.yaml`
  auto-generates one). Without it, a random key is used per process start,
  which just means everyone's logged out on every restart — not a security
  hole, just an annoyance.
- `PORT` — set by Render automatically.
- `DATA_DIR` — where the local-fallback `ops.db` and `journal/` live.
  Defaults to `data` (this repo's original local-dev path) when unset.
- `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` — see step 5 above. Unset means
  `ops.db` is a local file under `DATA_DIR` instead.
- `BACKUP_TOKEN` — see step 6. Auto-generated by `render.yaml`; also needs
  copying into a GitHub Actions secret for the weekly cron to authenticate.
- `PUSH_TOKEN` — see step 7. Auto-generated by `render.yaml`; also needs
  copying into a GitHub Actions secret for the hourly push-check cron to
  authenticate.

### 9. Run locally

    python -m src.cli check     # sanity check config + secrets, no network
    python app.py                # dev server on :5000
    # or:
    python -m src.cli today      # render a static copy to out/dashboard.html

### 10. Deploy (Render free tier)

Push this repo to GitHub, connect it in the Render dashboard ("New +" →
"Blueprint" — it picks up `render.yaml` from the **repo root**, which sets
`rootDir: silas-ops` so the build/start commands run against this
subfolder), set `APP_PASSWORD`, `TURSO_DATABASE_URL`, and
`TURSO_AUTH_TOKEN` in the Render env var UI (all marked `sync: false` so
none are ever in the repo). Without the two Turso vars set, the app still
deploys and runs fine — `ops.db` just reverts to a local file that gets
wiped on the next redeploy, same as if you'd never read this section.
`BACKUP_TOKEN` and `PUSH_TOKEN` are auto-generated by `render.yaml` — see
steps 6 and 7 above for the one-time GitHub Actions secrets they need to
be paired with.

Long-term, the build spec's other flagged option is moving to a Raspberry
Pi + Tailscale setup instead of any of this — that also removes the cold
start, and keeps API tokens off both Render's and Turso's servers. Not
done here; noted as the natural next step if that ever matters more than
the convenience of a cloud deploy.

## What's editable from the phone vs. baked into code vs. a config file

Same three-tier split as the original spec:

- **`/settings` (SQLite):** habits, journal prompts, course deadlines,
  priority order, overtraining guards, wake/sleep window.
- **Baked into code:** periodization/collision/streak/correlation math, all
  API clients, rendering, the shuffle-bag mechanism, the tag/quadrant/
  estimate parsing convention.
- **Config files (`config/*.yaml`), edited directly, rarely:** term
  start/end/exam period/reading week, course code list, the periodization
  anchor date and build/deload week counts, the weekly training template,
  races, nutrition targets.

## Not built

The one allowed AI add-on (an isolated, removable endpoint that calls the
Anthropic API to write a 2-3 sentence daily brief from the already-computed
state) — the spec says build it only if asked, and it hasn't been.
