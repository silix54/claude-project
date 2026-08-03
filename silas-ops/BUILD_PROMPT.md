# Silas Ops — build spec

Build me a personal operations dashboard. This file is the complete spec —
read all of it before writing code. If a scaffold zip (`silas-ops-scaffold/`)
is sitting alongside this file, extract it into the project root first:
several modules below are already implemented and tested, and the notes on
each say so explicitly. Don't rewrite those from scratch — extend them.

## Purpose, and the philosophy that shapes every decision below

This is not an "everything dashboard." The daily view is a ten-second
glance, not a report. The actual constraint being managed is energy and
decision fatigue, not time — there is usually enough time on paper. So the
daily view shows today's free windows and the one or two things that must
happen, and stays silent otherwise. A separate Sunday view does the fuller
planning session. A separate Reflect view handles habits, mood, journaling,
and devotions — that's a different job again (self-awareness over time),
and doesn't belong in a morning glance either.

**No AI or LLM dependency anywhere in the core system.** Every piece of
this — periodization math, calendar reads, collision detection, habit/mood
correlation — is deterministic Python. It should work exactly the same with
every AI product on earth turned off. The one allowed exception: an
optional, isolated add-on that calls the Anthropic API to write a two or
three sentence daily brief from the already-computed state. Build this only
if asked, and keep it removable without touching anything else.

**Journal content is private and is never parsed, summarized, or sent
anywhere.** Mood and energy are deliberately separate, lightweight,
structured 1-5 ratings, logged alongside the journal but never derived from
its text. This is what makes real correlation possible without ever turning
the journal into model input. Do not build a feature that reads journal
text programmatically, even if it seems useful, without being asked
explicitly.

## Architecture

- Python + Flask, single small server, deployed to Render's free tier to
  start (cold start of 30-60s after 15 minutes idle is an accepted
  tradeoff for a 1-2x/day personal check; a Raspberry Pi + Tailscale setup
  is the natural upgrade later if that's annoying, since it removes both
  the cold start and keeps API tokens off a third party's server — but
  don't build that now, just don't architect anything that would make it
  hard to move later).
- SQLite (`data/ops.db`) holds everything that should be editable from a
  phone: habits, mood/energy logs, journal prompts and entries, devotions
  logs, and a generic settings table (priority order, guard thresholds,
  wake/sleep window, course deadlines). A settings page with real forms
  reads and writes this — a database that can only be edited by hand-editing
  a file defeats the purpose.
- Two YAML files hold the two things that change once a term and are fine
  to edit directly in a text editor: `config/term.yaml` (term start/end,
  exam period, reading week) and `config/training.yaml` (the periodization
  anchor date, build/deload week counts, weekly session template, race
  dates, nutrition targets, overtraining guards). Read fresh on every
  request with `yaml.safe_load`, no caching.
- htmx plus a light touch of Alpine.js for interactivity — tap-to-triage
  tasks, quick-add forms that post and swap without a full reload. No
  React, no build step, no bundler. This is a solo-maintained personal tool
  and should stay that simple.
- Single shared password, session cookie. No user accounts — there's only
  ever one user.
- Design system: IBM Plex Mono for data/numbers, IBM Plex Sans Condensed
  for headers. Palette: field `#E8E6E1`, ink `#16181D`, signal `#1F4B99`,
  alert `#A8431C`, muted `#6E7278`, rule `#C9C5BC`. Read as an operations
  brief, not a consumer productivity app — no chart libraries, charts and
  heatmaps are hand-built SVG/CSS matching this palette exactly.

## Data sources and auth scopes

- **Google Calendar** — OAuth, `calendar.readonly`. Read-only, always. The
  dashboard should never write to the calendar.
- **Google Tasks** — OAuth, `tasks` (read/write). This is the task backend
  — no flat-file task parser. Google Tasks rows have a native creation
  timestamp, which is exactly what's needed to detect tasks that have
  quietly stalled — use it directly, don't build custom age-tracking.
  Parse a `@tag !quadrant ~estimate` convention out of the task notes field
  (tags: school/work/career/faith/fitness/admin; quadrants: now/plan/
  quick/drop, mapping to the Eisenhower matrix).
- **Strava** — OAuth, read-only. Covers all cardio training, since Garmin
  and Google Health both already sync there — no separate Garmin
  integration needed, and don't build one; the unofficial Garmin API is a
  ToS gray area and unnecessary here.
- **Google Drive** — OAuth, `drive.file` scope specifically, not broader
  Drive access. This scope means the app can only ever see and manage
  files it created itself. Used only to mirror journal entries.
- **No Hevy** — no Pro subscription, so no API access. Strength sessions
  are logged through a quick-add form built into the dashboard instead
  (exercise, sets, reps, weight — a few seconds after finishing a lift).

## Branch 1 — daily view (`/`)

- Signature visual: a day-bar showing free/open windows against committed
  blocks, not just a list of events — the open windows are the actionable
  information, since energy/decisions are the real constraint.
- Today's calendar events, list form.
- Slate: today's task priorities. Overdue and due-today pinned to the top,
  then ranked by Eisenhower quadrant, capped at ~5 so it stays honest about
  what actually gets attention today.
- Ahead: deadlines inside a rolling window, and a "collision watch" section
  that **only appears when something is actually flagged** — silence is
  the correct default state, meaning nothing needs attention. A collision
  is a week where deadlines, a reserve weekend, a deload week, and/or a
  race stack up; score severity (clear/watch/high) from deadline count,
  estimated hours, and whether flags co-occur.
- Body: today's planned training session from the weekly template
  (adjusted for deload weeks — drop Zone 4 intervals, cut volume ~40%),
  current block/week label, a compliance streak from logged sessions, and
  nutrition targets. Flag explicitly if consecutive training days exceed
  the configured guard — this person has a documented history of
  under-recovering if not checked, so this guard is not optional.
- A "this week" focus banner, persisted from the Sunday planning session,
  showing 1-3 priorities across every day until the next Sunday session.
- If the Calendar API call fails, fall back to the last successfully
  cached fetch and show a small "not live" indicator — never hard-fail the
  page just because the network or an OAuth token is having a bad day.

## Branch 2 — Sunday planning (`/plan`)

A guided session, not a longer report. Four sections in this order:

1. **Review (last 7 days).** Training: sessions planned vs. actually
   logged, and whether the overtraining guard tripped. Tasks: completion
   count, plus a clearly separate flagged list of tasks that have been open
   7+ days (using Google Tasks' native creation date). Optional single
   weight check-in field.
2. **Ahead (next 7 days only,** tighter than the daily view's rolling
   collision watch). Calendar load, deadlines actually due this week,
   deload/reserve-weekend/race status for the coming week specifically.
3. **Triage.** Every open task, one of three actions per task — keep this
   week / push a week / drop — via htmx, writing back to Google Tasks live,
   no page reload.
4. **Commit.** Pick 1-3 priorities for the week. Save to the settings
   table; this is what the daily view's focus banner reads all week.

## Branch 3 — Reflect (`/reflect`)

This is a distinct view you'd open deliberately, not a daily habit — don't
fold it into the morning glance.

**Habits.** Fully user-editable: add, rename, archive from `/settings`, no
code change ever required for a new habit. Displayed as a GitHub-style
contribution heatmap — one row per habit, one column per day, shaded if
logged done, with a per-row current streak count.

**Mood and energy.** A daily 1-5 rating for each, plus an optional
one-word free-text tag and a short note. This is the input to all
correlation math — deliberately not derived from journal text (see the
privacy note above). Rendered as an SVG line chart: solid line for mood,
dashed line for energy, with a shaded band around the mood line showing
the trailing 14-day rolling standard deviation — the width of that band
*is* the visualization of emotional stability, wider means less steady.

**Habit-mood correlation.** For each habit: mean mood and mean energy on
days it was logged done versus not done, plus a Pearson correlation
coefficient between the binary done/not-done signal and mood. Gate this at
a minimum of 14 overlapping days (mood logged AND the comparison is
meaningful, i.e. at least a handful of days on each side) — below that
threshold, show "not enough data yet," not a number. Language in the UI
must stay hedged throughout: "a pattern worth noticing, not a verdict."
Never assert causation. Never phrase this as a diagnosis or an
interpretation of *why* — just the numbers, for the person to draw their
own conclusions from.

**Journal.** Three fixed prompts every day:
  - What am I grateful for right now?
  - When was I emotionally disturbed? How did I respond?
  - What do I need to talk about with others?

Plus one rotating prompt per day from an editable pool, drawn via a
shuffle-bag (shuffle the whole pool once, work through it in order with no
repeats, reshuffle once exhausted — avoids the same prompt appearing twice
in a row). All prompts — fixed and rotating — are editable from
`/settings`: add, edit text, remove.

Each day's entry saves as its own file, `journal/YYYY-MM-DD.md`, and syncs
to a Google Drive folder via the `drive.file` scope. Never read
programmatically by anything except the save/sync path itself.

**Devotions.** Checkbox, a passage field (free text — "John 3", "Psalm
23"), and a note. Same streak mechanism as the general habit tracker under
the hood, but rendered as its own prominent block on the dashboard rather
than folded into the generic habit grid — this one is structurally more
central than a typical habit and should read that way visually.

**Worth adding once the above is solid** (scope, don't build yet unless
asked): an "on this day" callback surfacing the journal/mood entry from
exactly 1 week / 1 month / 1 year ago; a monthly extremes recap (best and
hardest day by self-rated mood, longest habit streaks — pure fact
surfacing, no interpretation attached); a frequency count of mood-log tags
over a period; an energy-vs-training-load overlay using the same
correlation math already built, against schedule data instead of habits; a
separate, unprompted free-write box distinct from the 3+1 journal prompts,
with an optional auto-purge window for anything that shouldn't accumulate
indefinitely.

## What's editable from the phone vs. baked into code vs. a config file

**Editable via `/settings` (SQLite-backed):** habits (add/rename/archive),
journal prompts (fixed and rotating, fully editable), course deadlines,
priority order, overtraining guard thresholds, wake/sleep window used for
computing free windows.

**Baked into code, changed only by changing logic:** the periodization
block/deload calculation, collision severity scoring, streak calculation,
the Pearson correlation and rolling stability math, all API client code,
rendering and layout, the shuffle-bag rotation mechanism, the
`@tag !quadrant ~estimate due:` parsing convention itself.

**Config files, edited directly and rarely:** term start/end/exam
period/reading week dates (`config/term.yaml`); the periodization anchor
date and build/deload week counts (`config/training.yaml`). These change
once a term — a text-file edit is the right amount of friction for
something that infrequent, not a reason to build a settings-page control
for it.

## Already built and verified — extend, don't replace

If the scaffold zip is present, these are implemented and tested:

- `src/periodization.py` — block/deload state machine from one anchor
  date. Verified: deload week anchors land on the intended Mondays.
- `src/gcal.py` — Google Calendar OAuth + read, with an offline cache
  fallback so a network failure never blanks the page.
- `src/assemble.py`, `src/render.py` — the daily view's state assembly and
  HTML rendering, including the day-bar signature element.
- `src/db.py` — the full SQLite schema and CRUD for habits, mood/energy,
  journal prompts/entries, devotions, and settings.
- `src/reflect.py` — Pearson correlation and rolling stability math.
  Verified against seeded synthetic data with a deliberately baked-in
  habit/mood relationship: correctly surfaced at r=0.41, while two
  uncorrelated control habits correctly returned near-zero r. (An earlier
  version of this had a join bug that silently made every "without" group
  empty — fixed. Worth writing a quick regression test around this join
  specifically before building further on top of it.)
- `src/render_reflect.py` — habit heatmap, mood/energy SVG chart,
  correlation summary, styled consistently with `render.py`.
- `src/tasks.py` — the flat-file `@tag !quadrant` parser. This is
  superseded by Google Tasks per the spec above; kept only as a reference
  for the parsing convention, don't wire it into the final app.

## Suggested build order

1. Flask skeleton, password gate, Google OAuth (Calendar + Tasks + Drive
   scopes as specified above).
2. Wire the existing periodization/collision/render modules into the `/`
   route.
3. Strava OAuth, wire into the Body section.
4. `/settings` — CRUD forms for habits, prompts, deadlines, priority
   order, guards.
5. `/reflect` — wire the existing db.py/reflect.py/render_reflect.py
   modules into a route (this part is the most complete already).
6. Journal quick-add form, Drive sync via `drive.file`.
7. `/plan` — Sunday view, htmx-based triage.
8. Push notifications (Web Push API + service worker) for devotions,
   task, and deadline reminders.
9. Deploy to Render's free tier.
