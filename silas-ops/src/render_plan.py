"""The /plan view. Same design system as render.py, imported directly.
Four sections in a fixed order: Review, Ahead, Triage, Commit. Triage rows
are htmx-live — each action posts and swaps without a full reload, per the
build spec's "no page reload" requirement for the Sunday session.
"""

from __future__ import annotations
from datetime import timedelta

from .render import CSS, FIELD, INK, SIGNAL, ALERT, MUTE, RULE, SUCCESS, esc, dur
from .chrome import NO_FLASH_SCRIPT, THEME_TOGGLE_TAG, nav_bar

CSS_EXTRA = f"""
.triage li{{display:flex;gap:9px;padding:7px 0;border-bottom:1px solid {RULE};
 align-items:center;font-size:12.5px}}
.triage .tt{{flex:1}}
.triage .tm{{font-size:10px;color:{MUTE};letter-spacing:.04em;white-space:nowrap;margin-right:8px}}
.triage button{{font:11px 'IBM Plex Mono',monospace;letter-spacing:.06em;text-transform:uppercase;
 background:none;border:1px solid {RULE};color:{INK};padding:4px 9px;cursor:pointer;margin-left:5px}}
.triage button:hover{{border-color:{SIGNAL};color:{SIGNAL}}}
.triage button.keep:hover{{border-color:{SUCCESS};color:{SUCCESS}}}
.triage button.drop:hover{{border-color:{ALERT};color:{ALERT}}}
.review-row{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid {RULE};
 font-size:12.5px}}
.review-row b{{font-variant-numeric:tabular-nums}}
.commit{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
.commit input[type=text]{{flex:1;min-width:160px;font:12.5px 'IBM Plex Mono',monospace;
 background:{FIELD};border:1px solid {RULE};padding:7px 9px;color:{INK}}}
.commit button,form.wt button{{font:11px 'IBM Plex Sans Condensed',sans-serif;letter-spacing:.06em;
 text-transform:uppercase;background:{INK};color:{FIELD};border:none;padding:8px 16px;cursor:pointer}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}}
.chips span{{border:1px solid {SIGNAL};color:{SIGNAL};font-size:10.5px;letter-spacing:.06em;
 text-transform:uppercase;padding:4px 9px}}
form.wt{{display:flex;gap:8px;margin-top:10px}}
form.wt input{{width:90px;font:12.5px 'IBM Plex Mono',monospace;background:{FIELD};
 border:1px solid {RULE};padding:7px 9px;color:{INK}}}
"""


def _review(r) -> str:
    guard = (f'<p class="flag">Overtraining guard tripped this week — {r["streak"]}-day streak.</p>'
            if r["guard_tripped"] else "")
    stalled = ""
    if r["stalled"]:
        rows = "".join(f'<li><span>{esc(t.text)}</span></li>' for t in r["stalled"])
        stalled = f'<h3>Stalled 7+ days</h3><ul class="ev">{rows}</ul>'
    else:
        stalled = '<h3>Stalled 7+ days</h3><p class="empty">Nothing stuck.</p>'
    return f"""
<div class="review-row"><span>Training sessions logged vs planned</span>
<b>{r['logged_days']} / {r['planned_days']}</b></div>
<div class="review-row"><span>Tasks completed</span><b>{r['tasks_completed']}</b></div>
{guard}
{stalled}
<h3>Weight check-in</h3>
<form class="wt" hx-post="/plan/weight" hx-swap="outerHTML" hx-target="closest form">
<input type="number" step="0.1" name="weight_lb" placeholder="lb">
<input type="text" name="note" placeholder="note (optional)">
<button type="submit">Log</button></form>"""


def _ahead(a) -> str:
    dl = ""
    if a["deadlines"]:
        rows = "".join(f'<li><b>{d["days"]}d</b><span>{esc(d["course"])} — {esc(d["title"])}</span></li>'
                       for d in a["deadlines"])
        dl = f'<h3>Due this week</h3><ul class="ev">{rows}</ul>'
    else:
        dl = '<h3>Due this week</h3><p class="empty">Nothing due.</p>'
    flags = f'<p class="note">{esc(", ".join(a["flags"]))}</p>' if a["flags"] else ""
    return f"""
<div class="review-row"><span>Week of</span><b>{a['week_of'].strftime('%b %-d')}</b></div>
<div class="review-row"><span>Calendar load</span><b>{dur(a['load_minutes'])} · {a['event_count']} events</b></div>
<div class="review-row"><span>Training</span><b>{esc(a['cycle_label'])}</b></div>
{flags}
{dl}"""


def _triage_row(t) -> str:
    meta = []
    if t.quadrant:
        meta.append(t.quadrant)
    if t.tag:
        meta.append("@" + t.tag)
    if t.due:
        meta.append(t.due.strftime("%b %-d"))
    return f"""<li id="triage-{t.id}"><span class="tt">{esc(t.text)}</span>
<span class="tm">{esc(" · ".join(meta))}</span>
<button class="keep" hx-post="/plan/triage/{t.id}?action=keep" hx-target="#triage-{t.id}" hx-swap="outerHTML">Keep</button>
<button hx-post="/plan/triage/{t.id}?action=push" hx-target="#triage-{t.id}" hx-swap="outerHTML">+1wk</button>
<button class="drop" hx-post="/plan/triage/{t.id}?action=drop" hx-target="#triage-{t.id}" hx-swap="outerHTML">Drop</button>
</li>"""


def triage_list(tasks) -> str:
    if not tasks:
        return '<p class="empty">Nothing open.</p>'
    return f'<ul class="triage">{"".join(_triage_row(t) for t in tasks)}</ul>'


def triage_done_row() -> str:
    return '<li style="opacity:.4">triaged</li>'


def _commit(weekly_focus) -> str:
    chips = "".join(f"<span>{esc(p)}</span>" for p in weekly_focus)
    return f"""
<div class="chips">{chips}</div>
<form class="commit" hx-post="/plan/commit" hx-target="#commit-section" hx-swap="innerHTML">
<input type="text" name="p1" placeholder="Priority 1" value="{esc(weekly_focus[0]) if len(weekly_focus)>0 else ''}">
<input type="text" name="p2" placeholder="Priority 2 (optional)" value="{esc(weekly_focus[1]) if len(weekly_focus)>1 else ''}">
<input type="text" name="p3" placeholder="Priority 3 (optional)" value="{esc(weekly_focus[2]) if len(weekly_focus)>2 else ''}">
<button type="submit">Commit</button></form>"""


def commit_section(weekly_focus) -> str:
    return _commit(weekly_focus)


def render_plan(state: dict) -> str:
    from datetime import date
    d = state["date"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plan — ops</title>
{NO_FLASH_SCRIPT}
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}{CSS_EXTRA}</style></head><body>
{nav_bar('plan')}
<div class="wrap">
<header><h1>Sunday plan</h1><div class="dtg">{d.strftime('%a %d %b')}</div></header>

<div class="grid" style="grid-template-columns:1fr">
<section><h2>1. Review — last 7 days</h2>{_review(state['review'])}</section>
<section><h2>2. Ahead — next 7 days</h2>{_ahead(state['ahead'])}</section>
<section><h2>3. Triage</h2>{triage_list(state['triage_tasks'])}</section>
<section><h2>4. Commit — this week's focus</h2>
<div id="commit-section">{_commit(state['weekly_focus'])}</div></section>
</div>
</div>
{THEME_TOGGLE_TAG}
</body></html>"""
