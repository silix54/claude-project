"""The /settings page — everything the spec marks as phone-editable:
habits, journal prompts, course deadlines, priority order, overtraining
guards, wake/sleep window. Plain POST-and-redirect forms (not htmx) — this
page is opened rarely and edited in bursts, not tapped through in real
time, so the simpler form model is the right amount of machinery.
"""

from __future__ import annotations

from .render import CSS, FIELD, INK, SIGNAL, ALERT, MUTE, RULE, esc
from .chrome import NO_FLASH_SCRIPT, THEME_TOGGLE_TAG, nav_bar

CSS_EXTRA = f"""
.settings-row{{display:flex;gap:9px;align-items:center;padding:6px 0;border-bottom:1px solid {RULE};
 font-size:12.5px}}
.settings-row .nm{{flex:1}}
.settings-row form{{display:inline-flex;gap:5px}}
input[type=text],input[type=number],input[type=date],input[type=time],select,textarea{{
 font:12.5px 'IBM Plex Mono',monospace;background:{FIELD};border:1px solid {RULE};padding:6px 8px;color:{INK}}}
textarea{{width:100%;min-height:44px}}
button,input[type=submit]{{font:10.5px 'IBM Plex Sans Condensed',sans-serif;letter-spacing:.08em;
 text-transform:uppercase;background:{INK};color:{FIELD};border:none;padding:6px 12px;cursor:pointer}}
button.danger{{background:{FIELD};color:{ALERT};border:1px solid {ALERT}}}
.addform{{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}}
.addform input,.addform select{{flex:1;min-width:100px}}
label.inline{{display:flex;gap:6px;align-items:center;font-size:11px;color:{MUTE};
 text-transform:uppercase;letter-spacing:.06em}}
.saved-flash{{background:{SIGNAL};color:{FIELD};font-size:11px;letter-spacing:.08em;
 text-transform:uppercase;padding:8px 14px;margin-bottom:14px;display:inline-block}}
@media(prefers-reduced-motion:no-preference){{
 .saved-flash{{animation:flash-out 2.5s ease forwards}}
 @keyframes flash-out{{0%,70%{{opacity:1}}100%{{opacity:0}}}}
}}
.archived{{margin-top:10px}}
.archived summary{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:{MUTE};cursor:pointer}}
.archived .settings-row{{opacity:.7}}
"""


def _archived_block(items, path: str, label_fn) -> str:
    if not items:
        return ""
    rows = "".join(f"""<div class="settings-row"><span class="nm">{label_fn(x)}</span>
<form method="post" action="/settings/{path}/{x['id']}/unarchive">
<button>Restore</button></form></div>""" for x in items)
    return f"""<details class="archived"><summary>Archived ({len(items)})</summary>{rows}</details>"""


def _habits(habits, archived_habits) -> str:
    rows = "".join(f"""<div class="settings-row"><span class="nm">{esc(h['name'])}</span>
<form method="post" action="/settings/habits/{h['id']}/rename">
<input type="text" name="name" value="{esc(h['name'])}" size="16"><button>Rename</button></form>
<form method="post" action="/settings/habits/{h['id']}/archive" onsubmit="return confirm('Archive this habit? You can restore it from Archived below.')">
<button class="danger">Archive</button></form></div>""" for h in habits) or '<p class="empty">No habits yet.</p>'
    return f"""{rows}
<form class="addform" method="post" action="/settings/habits">
<input type="text" name="name" placeholder="New habit name" required>
<button type="submit">Add habit</button></form>
{_archived_block(archived_habits, 'habits', lambda h: esc(h['name']))}"""


def _prompts(prompts, kind_label, kind, archived_prompts) -> str:
    rows = "".join(f"""<div class="settings-row"><form method="post"
action="/settings/prompts/{p['id']}/edit" style="flex:1"><textarea name="text">{esc(p['text'])}</textarea>
<button>Save</button></form>
<form method="post" action="/settings/prompts/{p['id']}/archive" onsubmit="return confirm('Archive this prompt? You can restore it from Archived below.')">
<button class="danger">Archive</button></form></div>""" for p in prompts) or '<p class="empty">None.</p>'
    archived_of_kind = [p for p in archived_prompts if p['kind'] == kind]
    return f"""<h3>{kind_label}</h3>{rows}
<form class="addform" method="post" action="/settings/prompts">
<input type="hidden" name="kind" value="{kind}">
<input type="text" name="text" placeholder="New prompt" required>
<button type="submit">Add</button></form>
{_archived_block(archived_of_kind, 'prompts', lambda p: esc(p['text'][:60]))}"""


def _deadlines(deadlines, courses, archived_deadlines) -> str:
    rows = "".join(f"""<div class="settings-row"><span class="nm">{esc(d['course'])} —
{esc(d['title'])} · due {esc(d['due'])}{f" · {d['weight']}%" if d.get('weight') else ""}</span>
<form method="post" action="/settings/deadlines/{d['id']}/archive" onsubmit="return confirm('Archive this deadline? You can restore it from Archived below.')">
<button class="danger">Archive</button></form></div>""" for d in deadlines) or '<p class="empty">None loaded.</p>'
    opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in courses)
    return f"""{rows}
<form class="addform" method="post" action="/settings/deadlines">
<select name="course">{opts}</select>
<input type="text" name="title" placeholder="Title" required>
<input type="date" name="due" required>
<input type="number" step="1" name="weight" placeholder="Weight %">
<input type="number" step="0.5" name="est_hours" placeholder="Est hours">
<button type="submit">Add deadline</button></form>
{_archived_block(archived_deadlines, 'deadlines', lambda d: esc(f"{d['course']} — {d['title']}"))}"""


def _priority(order) -> str:
    return f"""<form method="post" action="/settings/priority-order">
<input type="text" name="order" value="{esc(', '.join(order))}" style="width:100%">
<p class="sub">Comma-separated, highest priority first.</p>
<button type="submit">Save</button></form>"""


def _guards(g) -> str:
    return f"""<form method="post" action="/settings/guards" class="addform">
<label class="inline">Max consecutive training days
<input type="number" name="max_consecutive_training_days" value="{g['max_consecutive_training_days']}"></label>
<label class="inline">Min sleep hours
<input type="number" step="0.5" name="min_sleep_hours" value="{g['min_sleep_hours']}"></label>
<label class="inline">Flag if sessions/week over
<input type="number" name="flag_if_sessions_per_week_over" value="{g['flag_if_sessions_per_week_over']}"></label>
<button type="submit">Save</button></form>"""


def _wake_sleep(wake, sleep) -> str:
    return f"""<form method="post" action="/settings/wake-sleep" class="addform">
<label class="inline">Wake <input type="time" name="wake" value="{esc(wake)}"></label>
<label class="inline">Sleep <input type="time" name="sleep" value="{esc(sleep)}"></label>
<button type="submit">Save</button></form>"""


def render_settings(state: dict, saved: bool = False) -> str:
    flash = '<p class="saved-flash">Saved.</p>' if saved else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Settings — ops</title>
{NO_FLASH_SCRIPT}
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}{CSS_EXTRA}</style></head><body>
{nav_bar('settings')}
<div class="wrap">
<header><h1>Settings</h1></header>
{flash}
<div class="grid" style="grid-template-columns:1fr">
<section><h2>Habits</h2>{_habits(state['habits'], state['archived_habits'])}</section>
<section><h2>Journal prompts</h2>
{_prompts(state['fixed_prompts'], 'Fixed (every day)', 'fixed', state['archived_prompts'])}
{_prompts(state['rotating_prompts'], 'Rotating pool', 'rotating', state['archived_prompts'])}</section>
<section><h2>Course deadlines</h2>{_deadlines(state['deadlines'], state['course_codes'], state['archived_deadlines'])}</section>
<section><h2>Priority order</h2>{_priority(state['priority_order'])}</section>
<section><h2>Overtraining guards</h2>{_guards(state['guards'])}</section>
<section><h2>Wake / sleep window</h2>{_wake_sleep(*state['wake_sleep'])}</section>
</div>
</div>
{THEME_TOGGLE_TAG}
</body></html>"""
