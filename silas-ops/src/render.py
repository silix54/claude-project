"""Render the dashboard. Single self-contained HTML file, no build step.

Design intent: an operations brief, not a productivity app. The signature
element is the day bar, which shows gaps rather than events, because the
constraint being managed here is energy and where it actually goes.

Color/theme tokens, the nav bar, and dark-mode wiring live in chrome.py —
imported here as FIELD/INK/etc (now CSS var() references, not literal
hex) so every existing {INK}, {FIELD}... interpolation below is already
theme-aware.
"""

from __future__ import annotations
import html
from datetime import datetime, time, date

from .chrome import (FIELD, SURFACE, INK, MUTE, RULE, SIGNAL, ALERT, SUCCESS,
                     THEME_VARS, NO_FLASH_SCRIPT, THEME_TOGGLE_TAG, NAV_CSS, nav_bar)


def esc(s):
    return html.escape(str(s))


def hm(dt):
    return dt.strftime("%H:%M")


def dur(m):
    h, mm = divmod(int(m), 60)
    return f"{h}h{mm:02d}" if h else f"{mm}m"


def _hours(hhmm: str) -> float:
    h, m = hhmm.split(":")
    return int(h) + int(m) / 60


def _pos(dt, wake, sleep):
    v = dt.hour + dt.minute / 60
    return max(0.0, min(100.0, (v - wake) / (sleep - wake) * 100))


def day_bar(s):
    wake, sleep = _hours(s["wake"]), _hours(s["sleep"])
    segs = []
    for e in s["events_today"]:
        if e.all_day:
            continue
        a, b = _pos(e.start, wake, sleep), _pos(e.end, wake, sleep)
        if b - a < 0.4:
            continue
        segs.append(f'<div class="blk" style="left:{a:.2f}%;width:{b-a:.2f}%" '
                    f'title="{esc(e.title)} {hm(e.start)}-{hm(e.end)}">'
                    f'<span>{esc(e.title)}</span></div>')
    for a, b in s["gaps"]:
        x, y = _pos(a, wake, sleep), _pos(b, wake, sleep)
        mins = int((b - a).total_seconds() // 60)
        lbl = f'<span class="gl">{dur(mins)}</span>' if y - x > 6 else ""
        segs.append(f'<div class="gap" style="left:{x:.2f}%;width:{y-x:.2f}%">{lbl}</div>')
    ticks = "".join(
        f'<div class="tick" style="left:{(h-wake)/(sleep-wake)*100:.2f}%"><b>{h:02d}</b></div>'
        for h in range(int(wake) + 1, int(sleep) + 1, 2))
    now = datetime.now()
    nowline = ""
    if s["date"] == date.today() and wake <= now.hour + now.minute / 60 <= sleep:
        nowline = f'<div class="now" style="left:{_pos(now, wake, sleep):.2f}%"></div>'
    return f'<div class="bar">{"".join(segs)}{ticks}{nowline}</div>'


QUICKADD_TASK = """<form class="quickadd" hx-post="/quickadd/task" hx-target="#slate" hx-swap="outerHTML">
<input type="text" name="title" placeholder="New task" required>
<select name="quadrant"><option value="">quadrant</option>
<option value="now">now</option><option value="plan">plan</option>
<option value="quick">quick</option><option value="drop">drop</option></select>
<select name="tag"><option value="">tag</option>
<option>school</option><option>work</option><option>career</option>
<option>faith</option><option>fitness</option><option>admin</option></select>
<input type="number" name="est_minutes" placeholder="min" style="width:56px">
<input type="date" name="due">
<button type="submit">Add</button></form>"""


def _tasks(s):
    body = '<p class="empty">Nothing open.</p>' if not s["slate"] else _slate_rows(s["slate"])
    return f'<div id="slate">{body}{QUICKADD_TASK}</div>'


def _slate_rows(slate):
    rows = []
    for t in slate:
        cls = "od" if t.overdue else ("dt" if t.due_today else "")
        meta = []
        if t.quadrant:
            meta.append(t.quadrant)
        if t.tag:
            meta.append("@" + t.tag)
        if t.est_minutes:
            meta.append(dur(t.est_minutes))
        if t.due:
            meta.append("overdue" if t.overdue else t.due.strftime("%b %-d"))
        rows.append(f'<li class="{cls}"><span class="tt">{esc(t.text)}</span>'
                    f'<span class="tm">{esc(" · ".join(meta))}</span></li>')
    return f'<ul class="slate">{"".join(rows)}</ul>'


def _events(s):
    if not s["events_today"]:
        return '<p class="empty">Calendar clear.</p>'
    rows = []
    for e in s["events_today"]:
        t = "all day" if e.all_day else f"{hm(e.start)}–{hm(e.end)}"
        loc = f'<span class="lo">{esc(e.location)}</span>' if e.location else ""
        rows.append(f'<li><b>{esc(t)}</b><span>{esc(e.title)}</span>{loc}</li>')
    return f'<ul class="ev">{"".join(rows)}</ul>'


def _training(s):
    c = s["cycle"]
    tag = '<em class="dl">deload</em>' if c.is_deload else ""
    items = "".join(
        f'<li><b>{esc(x.get("type"))}</b><span>{esc(x.get("name") or x.get("note",""))}'
        f'{" · Z" + str(x["zone"]) if x.get("zone") else ""}</span></li>'
        for x in s["planned_sessions"]) or '<li><span class="empty">Nothing planned.</span></li>'
    comp = s["compliance"]
    warn = ok = ""
    if comp["streak"] >= s["guards"]["max_consecutive_training_days"]:
        warn = (f'<p class="flag">{comp["streak"]} consecutive training days. '
                f'Guard is {s["guards"]["max_consecutive_training_days"]}. Take the rest day.</p>')
    elif comp["streak"] > 0:
        ok = f'<p class="sub ok">{comp["streak"]}-day streak, under the guard — on track.</p>'
    note = f'<p class="note">{esc(s["deload_rules"]["note"])}</p>' if c.is_deload else ""
    recent = s.get("recent_activities") or []
    recent_html = ""
    if recent:
        rows = "".join(f'<li><b>{esc(a.type)}</b><span>{esc(a.name)} · {dur(a.minutes)}'
                       f'{f" · {a.distance_km}km" if a.distance_km else ""}</span></li>'
                       for a in reversed(recent))
        recent_html = f'<h3>Recent (Strava)</h3><ul class="sess">{rows}</ul>'
    quickadd = """<h3>Log strength</h3>
<form class="quickadd" hx-post="/quickadd/strength" hx-target="this" hx-swap="outerHTML">
<input type="text" name="exercise" placeholder="Exercise" required>
<input type="number" name="sets" placeholder="sets" style="width:52px">
<input type="number" name="reps" placeholder="reps" style="width:52px">
<input type="number" step="0.5" name="weight_lb" placeholder="lb" style="width:60px">
<button type="submit">Log</button></form>"""
    return (f'<div class="cyc">{esc(c.label)} {tag}</div>{note}'
            f'<ul class="sess">{items}</ul>{warn}{ok}'
            f'<p class="sub">{comp["logged"]} sessions logged in 7 days · '
            f'last {esc(comp["last"] or "never")}</p>{recent_html}{quickadd}')


def _fuel(s):
    n = s["nutrition"]
    k, p, f, c = n["target_kcal"], n["protein_g"], n["fat_g"], n["carb_g"]
    w = s["weight_log"][-1]["weight_lb"] if s["weight_log"] else "—"
    return (f'<div class="macros">'
            f'<div><b>{k[0]}–{k[1]}</b><span>kcal</span></div>'
            f'<div><b>{p[0]}–{p[1]}</b><span>protein g</span></div>'
            f'<div><b>{c[0]}–{c[1]}</b><span>carb g</span></div>'
            f'<div><b>{f[0]}–{f[1]}</b><span>fat g</span></div></div>'
            f'<p class="sub">Last weigh-in {esc(w)} lb · target {n["bodyweight_lb_target"]} lb · '
            f'{esc(n["goal"])}</p>')


def _ahead(s):
    out = []
    if s["deadlines"]:
        rows = "".join(
            f'<li class="{"od" if d["days"] < 0 else ""}"><b>{d["days"]:+d}d</b>'
            f'<span>{esc(d["course"])} — {esc(d["title"])}'
            f'{" · " + str(d["weight"]) + "%" if d.get("weight") else ""}</span></li>'
            for d in s["deadlines"])
        out.append(f'<h3>Deadlines</h3><ul class="ev">{rows}</ul>')
    else:
        out.append('<h3>Deadlines</h3><p class="empty">None loaded. '
                   'Add them to config/term.yaml as syllabi land.</p>')

    hot = [c for c in s["collisions"] if c["severity"] != "clear"]
    if hot:
        rows = "".join(
            f'<li class="{c["severity"]}"><b>{c["week_of"].strftime("%b %-d")}</b>'
            f'<span>{len(c["deadlines"])} deadline(s) · ~{c["est_hours"]}h'
            f'{" · " + esc(", ".join(c["flags"])) if c["flags"] else ""}</span></li>'
            for c in hot)
        out.append(f'<h3>Collision watch</h3><ul class="ev">{rows}</ul>')

    if s["races"]:
        rows = "".join(f'<li><b>{r["days"]}d</b><span>{esc(r["name"])}</span></li>'
                       for r in s["races"])
        out.append(f'<h3>Races</h3><ul class="ev">{rows}</ul>')
    return "".join(out)


CSS = THEME_VARS + f"""
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:{FIELD};color:{INK};font:14px/1.5 'IBM Plex Mono',ui-monospace,monospace;
 padding:28px 22px 60px;-webkit-font-smoothing:antialiased;transition:background .15s,color .15s}}
.wrap{{max-width:1180px;margin:0 auto}}
h1,h2,h3,.lbl{{font-family:'IBM Plex Sans Condensed','IBM Plex Sans',sans-serif}}
header{{display:flex;justify-content:space-between;align-items:flex-end;
 border-bottom:2px solid {INK};padding-bottom:10px;margin-bottom:4px;flex-wrap:wrap;gap:10px}}
h1{{font-size:30px;font-weight:600;letter-spacing:-.02em;line-height:1}}
.dtg{{font-size:11px;color:{MUTE};letter-spacing:.14em;text-transform:uppercase;
 text-align:right;line-height:1.7}}
.stale{{color:{ALERT}}}
.focus{{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:11px;
 letter-spacing:.08em;text-transform:uppercase;color:{SIGNAL};border:1px solid {SIGNAL};
 padding:7px 12px;margin-top:14px}}
.focus b{{color:{INK};font-family:'IBM Plex Sans Condensed',sans-serif}}
.bar{{position:relative;height:52px;margin:26px 0 8px;border:1px solid {RULE};
 background:repeating-linear-gradient(90deg,transparent 0 3px,rgba(0,0,0,.03) 3px 4px)}}
.blk{{position:absolute;top:0;bottom:14px;background:{INK};color:{FIELD};overflow:hidden;
 font-size:10px;display:flex;align-items:center;padding:0 4px;border-right:1px solid {FIELD}}}
.blk span{{white-space:nowrap;text-overflow:ellipsis;overflow:hidden}}
.gap{{position:absolute;top:0;bottom:14px;display:flex;align-items:center;justify-content:center}}
.gl{{font-size:10px;color:{SIGNAL};letter-spacing:.06em}}
.tick{{position:absolute;bottom:0;height:14px;border-left:1px solid {RULE};padding-left:3px}}
.tick b{{font-size:9px;color:{MUTE};font-weight:400}}
.now{{position:absolute;top:-5px;bottom:8px;width:2px;background:{ALERT}}}
.legend{{font-size:10px;color:{MUTE};letter-spacing:.1em;text-transform:uppercase;
 display:flex;gap:18px;margin-bottom:26px}}
.legend b{{color:{SIGNAL};font-weight:500}}
.grid{{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:20px}}
section{{background:{SURFACE};border:1px solid {RULE};border-top:2px solid {INK};
 padding:14px 16px 18px}}
h2{{font-size:11px;letter-spacing:.18em;text-transform:uppercase;font-weight:600;margin-bottom:11px}}
h3{{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:{MUTE};
 font-weight:600;margin:16px 0 6px}}
h3:first-child{{margin-top:0}}
ul{{list-style:none}}
.ev li,.slate li{{display:flex;gap:9px;padding:5px 0;border-bottom:1px solid {RULE};
 align-items:baseline;font-size:12.5px}}
.ev li b{{flex:0 0 72px;color:{MUTE};font-weight:500;font-variant-numeric:tabular-nums}}
.ev li span{{flex:1}}
.lo{{flex:0 0 auto!important;font-size:10px;color:{MUTE}}}
.slate .tt{{flex:1}}
.slate .tm{{font-size:10px;color:{MUTE};letter-spacing:.04em;white-space:nowrap}}
.od .tt,.od span,.ev li.od span{{color:{ALERT}}}
.od b{{color:{ALERT}!important}}
.dt .tt{{font-weight:600}}
li.high b{{color:{ALERT}!important}}
li.high{{background:rgba(168,67,28,.07)}}
li.watch b{{color:{SIGNAL}!important}}
.ok,.ok b{{color:{SUCCESS}!important}}
.cyc{{font-family:'IBM Plex Sans Condensed',sans-serif;font-size:19px;font-weight:600;
 margin-bottom:4px}}
.dl{{color:{ALERT};font-size:12px;font-style:normal;letter-spacing:.1em;text-transform:uppercase}}
.sess li{{display:flex;gap:9px;padding:5px 0;border-bottom:1px solid {RULE};font-size:12.5px}}
.sess li b{{flex:0 0 72px;color:{SIGNAL};font-weight:500;text-transform:uppercase;font-size:10.5px;
 letter-spacing:.08em;padding-top:2px}}
.macros{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:{RULE};
 border:1px solid {RULE};margin-bottom:8px}}
.macros div{{background:{FIELD};padding:9px 10px}}
.macros b{{display:block;font-size:17px;font-weight:600;font-variant-numeric:tabular-nums}}
.macros span{{font-size:9.5px;color:{MUTE};letter-spacing:.12em;text-transform:uppercase}}
.sub,.note{{font-size:10.5px;color:{MUTE};margin-top:7px;letter-spacing:.03em}}
.note{{color:{SIGNAL}}}
.flag{{color:{ALERT};font-size:11.5px;margin-top:8px;border-left:2px solid {ALERT};padding-left:8px}}
.quickadd{{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}}
.quickadd input,.quickadd select{{font:11px 'IBM Plex Mono',monospace;background:{FIELD};
 border:1px solid {RULE};padding:5px 7px;color:{INK};flex:1;min-width:64px}}
.quickadd button{{font:10px 'IBM Plex Sans Condensed',sans-serif;letter-spacing:.06em;
 text-transform:uppercase;background:{INK};color:{FIELD};border:none;padding:6px 12px;cursor:pointer}}
.empty{{color:{MUTE};font-size:12px;font-style:italic}}
.cap{{display:flex;gap:22px;margin-bottom:14px;font-size:11px;color:{MUTE};
 letter-spacing:.1em;text-transform:uppercase}}
.cap b{{color:{INK};font-weight:600;font-size:15px;font-variant-numeric:tabular-nums}}
footer{{margin-top:34px;padding-top:9px;border-top:1px solid {RULE};font-size:10px;
 color:{MUTE};letter-spacing:.1em;text-transform:uppercase}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}.blk span{{display:none}}}}
@media(prefers-reduced-motion:no-preference){{section{{animation:f .4s ease both}}
 section:nth-child(2){{animation-delay:.06s}}section:nth-child(3){{animation-delay:.12s}}
 @keyframes f{{from{{opacity:0;transform:translateY(6px)}}}}}}
""" + NAV_CSS


def _focus_banner(s):
    wf = s.get("weekly_focus") or []
    if not wf:
        return ""
    items = "".join(f"<span>{esc(p)}</span>" for p in wf)
    return f'<div class="focus"><b>This week</b>{items}</div>'


def render(s) -> str:
    d = s["date"]
    stale = "" if s["calendar_live"] else '<div class="stale">calendar cached · not live</div>'
    if not s.get("strava_live", True):
        stale += '<div class="stale">strava cached · not live</div>'
    fm, cm = s["free_minutes"], s["committed_minutes"]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{d.strftime('%a %d %b')} — ops</title>
{NO_FLASH_SCRIPT}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<link rel="manifest" href="/static/manifest.json">
<style>{CSS}</style></head><body>
{nav_bar('daily')}
<div class="wrap">
<header>
  <h1>{d.strftime('%A %-d %B')}</h1>
  <div class="dtg">{esc(s['term']['name'])} · {esc(s['cycle'].label)}<br>
  generated {esc(s['generated'].replace('T',' '))}{stale}</div>
</header>

{_focus_banner(s)}
{day_bar(s)}
<div class="legend"><span>Committed</span><span><b>Open windows</b></span>
<span>{dur(fm)} open · {dur(cm)} of slate estimated</span></div>

<div class="cap">
  <span><b>{s['open_count']}</b> open</span>
  <span><b>{len(s['overdue'])}</b> overdue</span>
  <span><b>{len(s['events_today'])}</b> events</span>
  <span><b>{len(s['gaps'])}</b> windows</span>
</div>

<div class="grid">
  <section><h2>Today</h2>{_events(s)}<h3>Slate</h3>{_tasks(s)}</section>
  <section><h2>Ahead</h2>{_ahead(s)}</section>
  <section><h2>Body</h2>{_training(s)}<h3>Fuel</h3>{_fuel(s)}</section>
</div>

<footer>Read only against Google Calendar · tasks via Google Tasks</footer>
<script src="/static/push.js"></script>
</div>
{THEME_TOGGLE_TAG}
</body></html>"""
