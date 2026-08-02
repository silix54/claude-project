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
  deadlines, strength/weight logs, settings, push subscriptions.
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

### 5. Environment variables

- `APP_PASSWORD` — required. The single shared password.
- `FLASK_SECRET_KEY` — recommended in production (Render's `render.yaml`
  auto-generates one). Without it, a random key is used per process start,
  which just means everyone's logged out on every restart — not a security
  hole, just an annoyance.
- `PORT` — set by Render automatically.

### 6. Run locally

    python -m src.cli check     # sanity check config + secrets, no network
    python app.py                # dev server on :5000
    # or:
    python -m src.cli today      # render a static copy to out/dashboard.html

### 7. Deploy (Render free tier)

Push this repo to GitHub, connect it in the Render dashboard ("New +" →
"Blueprint" — it picks up `render.yaml` from the **repo root**, which sets
`rootDir: silas-ops` so the build/start commands run against this
subfolder), set `APP_PASSWORD` in the Render env var UI (marked
`sync: false` so it's never in the repo).

`data/ops.db` and `journal/` live on Render's ephemeral disk by default —
wiped on every redeploy. Attach a Render persistent disk once this is in
daily use, or move to the Raspberry Pi + Tailscale setup the build spec
flags as the natural next step (removes the cold start too).

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
