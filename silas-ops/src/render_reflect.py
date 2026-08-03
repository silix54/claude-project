"""The reflect view. Same design system as render.py (imported directly, not
duplicated) but this page has its own job: surfacing patterns across habits,
mood, and energy, honestly hedged. It is not the daily glance — you'd open
this on a Sunday, or when you actually want to look, not every morning.
"""

from __future__ import annotations
import html
from datetime import date, timedelta

from .render import FIELD, INK, SIGNAL, ALERT, MUTE, RULE, SUCCESS, esc
from .chrome import (NO_FLASH_SCRIPT, THEME_TOGGLE_TAG, nav_bar,
                     QUADRANT_COLORS, QUADRANT_LABELS, HABIT_COLORS)

CELL, GAP = 12, 3


def _habit_color(h: dict) -> str:
    """Identity color for this habit — which habit this is, cycled at
    creation (db.add_habit), stable across sessions. Unrelated to the
    quadrant colors (chrome.QUADRANT_COLORS): those mean task urgency,
    this means "which habit," and the two are never mixed at a call site.
    Falls back to neutral MUTE for any pre-migration row that somehow
    still has no color (shouldn't happen — db.init() backfills it)."""
    return HABIT_COLORS.get(h.get("color"), MUTE)


def _streak(logs: dict[str, bool], today: date) -> int:
    streak, cur = 0, today
    while logs.get(cur.isoformat()):
        streak += 1
        cur -= timedelta(days=1)
    return streak


def ring_col(h: dict, done: bool, streak: int) -> str:
    """One ring, standalone-renderable so the toggle route can hand back
    just this fragment and have it swap itself in place — hx-swap="none"
    (what the old chip row used) posts the toggle but never touches the
    DOM, so the ring would say "filled if logged done today" and then not
    actually fill until the next full page load. Outline is always the
    habit's identity color (readable even before tapping); filled the
    same color once done. Streak stays a fixed, already-AA-checked color
    (ink when done, muted when not) rather than the habit color — see
    habit_heatmap()'s docstring for why the identity palette can't carry
    body text/foreground content directly."""
    color = _habit_color(h)
    fill = f'<circle cx="22" cy="22" r="17" fill="{color}" opacity="0.22"/>' if done else ""
    return f"""<div class="hring-col">
<button class="hring" hx-post="/reflect/habit/{h['id']}/toggle" hx-target="closest .hring-col"
 hx-swap="outerHTML" aria-label="Toggle {esc(h['name'])}, logged {'done' if done else 'not done'} today">
<svg viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
{fill}<circle cx="22" cy="22" r="17" fill="none" stroke="{color}" stroke-width="2.5"
 opacity="{1 if done else 0.4}"/>
<text x="22" y="27" text-anchor="middle" font-size="13" font-weight="600"
 fill="{INK if done else MUTE}">{streak}</text>
</svg></button>
<span class="hring-name">{esc(h['name'])}</span></div>"""


def habit_ring_row(habits: list[dict], logs_by_habit: dict[int, dict[str, bool]],
                   done_today: dict[int, bool]) -> str:
    """Today's status per habit, one SVG ring each. Tapping toggles today's
    log — same htmx endpoint the old chip row used — and the ring itself
    swaps to reflect the new state immediately; see ring_col()."""
    if not habits:
        return ""
    today = date.today()
    cols = [ring_col(h, done_today.get(h["id"], False), _streak(logs_by_habit.get(h["id"], {}), today))
           for h in habits]
    return f'<div class="hrings">{"".join(cols)}</div>'


def habit_heatmap(habits: list[dict], logs_by_habit: dict[int, dict[str, bool]],
                  weeks: int = 12) -> str:
    """Filled cells use each habit's own identity color instead of one
    generic fill, so a row is recognizable by color alone. The habit-name
    label itself stays plain ink text rather than taking that color
    directly — three of the five identity colors don't clear the >=4.5:1
    AA text threshold (they're only checked to the decorative >=3:1 bar,
    since a ring/cell fill isn't body text) — identity is conveyed via a
    small swatch dot next to the name instead."""
    if not habits:
        return '<p class="empty">No habits yet. Add one in Settings.</p>'
    days = weeks * 7
    today = date.today()
    dates = [(today - timedelta(days=days - 1 - i)) for i in range(days)]

    rows = []
    for h in habits:
        logs = logs_by_habit.get(h["id"], {})
        color = _habit_color(h)

        def cell_color(done):
            if done is None:
                return RULE          # no data that day (habit didn't exist yet)
            return color if done else "#FFFFFF00"  # filled if done, transparent if skipped

        cells = "".join(
            f'<span class="cell" style="background:{cell_color(logs.get(d.isoformat()))}" '
            f'title="{d.isoformat()}"></span>' for d in dates)
        rows.append(f'<div class="hrow"><span class="hname">'
                    f'<i class="hswatch" style="background:{color}"></i>{esc(h["name"])}</span>'
                    f'<span class="hgrid">{cells}</span>'
                    f'<span class="hstreak">{_streak(logs, today)}d</span></div>')
    return f'<div class="heat">{"".join(rows)}</div>'


def _scale_y(v: float, top: float, bottom: float, lo=1.0, hi=5.0) -> float:
    v = max(lo, min(hi, v))
    return bottom - (v - lo) / (hi - lo) * (bottom - top)


def mood_chart(rows: list[dict], days: int = 30, width: int = 760, height: int = 180) -> str:
    """rows come from reflect.rolling_stability: date, mood, energy, stability."""
    rows = [r for r in rows if r.get("mood") is not None][-days:]
    if len(rows) < 2:
        return '<p class="empty">Log mood for a few more days to see the chart.</p>'

    top, bottom, left, right = 14, height - 22, 4, width - 4
    n = len(rows)
    step = (right - left) / max(1, n - 1)

    def pts(key):
        return [(left + i * step, _scale_y(r[key], top, bottom))
                for i, r in enumerate(rows) if r.get(key) is not None]

    mood_pts = pts("mood")
    energy_pts = pts("energy")

    band = []
    for i, r in enumerate(rows):
        if r.get("mood") is None:
            continue
        sd = r.get("stability") or 0
        x = left + i * step
        band.append((x, _scale_y(r["mood"] + sd, top, bottom)))
    for i, r in reversed(list(enumerate(rows))):
        if r.get("mood") is None:
            continue
        sd = r.get("stability") or 0
        x = left + i * step
        band.append((x, _scale_y(r["mood"] - sd, top, bottom)))
    band_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in band)

    mood_line = " ".join(f"{x:.1f},{y:.1f}" for x, y in mood_pts)
    energy_line = " ".join(f"{x:.1f},{y:.1f}" for x, y in energy_pts)

    gridlines = "".join(
        f'<line x1="{left}" y1="{_scale_y(v, top, bottom):.1f}" x2="{right}" '
        f'y2="{_scale_y(v, top, bottom):.1f}" stroke="{RULE}" stroke-width="1"/>'
        f'<text x="0" y="{_scale_y(v, top, bottom)+3:.1f}" font-size="9" fill="{MUTE}">{v}</text>'
        for v in (1, 3, 5))

    last = rows[-1]
    label = f'mood {last["mood"]} · energy {last.get("energy","—")}'
    if last.get("stability") is not None:
        label += f' · stability ±{last["stability"]}'

    return f"""<svg viewBox="0 0 {width} {height}" width="100%" height="{height}"
      role="img" aria-label="Mood and energy over time">
      {gridlines}
      <polygon points="{band_path}" fill="{SIGNAL}" opacity="0.10"/>
      <polyline points="{energy_line}" fill="none" stroke="{MUTE}" stroke-width="1.5"
        stroke-dasharray="3,3"/>
      <polyline points="{mood_line}" fill="none" stroke="{SIGNAL}" stroke-width="2"/>
    </svg>
    <p class="sub">{esc(label)} · shaded band is mood stability (trailing 14-day spread) ·
    solid = mood, dashed = energy</p>"""


def quadrant_chart(weekly: list[dict], width: int = 760, height: int = 150) -> str:
    """One 100%-stacked bar per week (last 6), proportion of that week's
    completed tasks in each Eisenhower quadrant — same 4 colors as the
    /plan matrix (chrome.QUADRANT_COLORS), so the two features read as one
    system. Stacked by proportion rather than raw count so a slow week and
    a busy week are still comparable in composition, which is the actual
    question this answers: reactive or deliberate, not how much got done."""
    if not any(w["total"] for w in weekly):
        return '<p class="empty">No completed, quadrant-tagged tasks yet.</p>'

    top, bottom, gap = 8, height - 24, 8
    n = len(weekly)
    bar_w = (width - gap * (n + 1)) / n
    bars = []
    for i, w in enumerate(weekly):
        x = gap + i * (bar_w + gap)
        total = w["total"]
        if not total:
            bars.append(f'<rect x="{x:.1f}" y="{bottom-2:.1f}" width="{bar_w:.1f}" '
                       f'height="2" fill="{RULE}"/>')
        else:
            y = bottom
            for key in ("now", "plan", "quick"):
                v = w[key]
                if not v:
                    continue
                seg_h = v / total * (bottom - top)
                y -= seg_h
                bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                           f'height="{seg_h:.1f}" fill="{QUADRANT_COLORS[key]}"/>')
            other = w["drop"] + w["none"]
            if other:
                seg_h = other / total * (bottom - top)
                y -= seg_h
                bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                           f'height="{seg_h:.1f}" fill="{MUTE}"/>')
        bars.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - 6}" font-size="9" '
                   f'fill="{MUTE}" text-anchor="middle">{w["week_of"].strftime("%b %-d")}</text>')

    legend = "".join(f'<span><i style="background:{QUADRANT_COLORS[k]}"></i>{QUADRANT_LABELS[k]}</span>'
                     for k in ("now", "plan", "quick", "drop"))
    return f"""<svg viewBox="0 0 {width} {height}" width="100%" height="{height}"
      role="img" aria-label="Completed tasks by quadrant, last 6 weeks">
      {"".join(bars)}
    </svg>
    <div class="qlegend">{legend}</div>
    <p class="sub">Share of each week's completed tasks by quadrant — reactive (now/quick)
    vs. deliberate (plan) at a glance, not how much got done.</p>"""


def correlation_summary(links, colors: dict[str, str] | None = None) -> str:
    colors = colors or {}
    if not links:
        return '<p class="empty">No habits yet.</p>'
    rows = []
    for l in links:
        swatch = f'<i class="hswatch" style="background:{colors.get(l.habit, MUTE)}"></i>'
        if not l.confident:
            need = max(0, 14 - (l.n_with + l.n_without))
            rows.append(f'<li class="dim"><b>{swatch}{esc(l.habit)}</b>'
                        f'<span>not enough overlapping days yet'
                        f'{f" — about {need} more" if need else ""}</span></li>')
            continue
        md = l.mood_delta
        direction = "higher" if (md or 0) > 0 else "lower" if (md or 0) < 0 else "no difference in"
        rows.append(
            f'<li><b>{swatch}{esc(l.habit)}</b><span>mood {abs(md) if md else 0} points {direction} '
            f'on days you did it ({l.mood_with} vs {l.mood_without}, n={l.n_with}/{l.n_without}) '
            f'· r={l.r_mood}</span></li>')
    return (f'<ul class="corr">{"".join(rows)}</ul>'
           f'<p class="sub">r is a correlation, not a cause — a pattern worth noticing, '
           f'not a verdict. Shown only once there\'s enough overlapping data (14+ days).</p>')


CSS_EXTRA = f"""
.qlegend{{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:10px;
 color:{MUTE};letter-spacing:.06em;text-transform:uppercase}}
.qlegend span{{display:inline-flex;align-items:center;gap:5px}}
.qlegend i{{display:inline-block;width:8px;height:8px;border-radius:1px}}
.hswatch{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;
 flex:0 0 auto}}
.hrings{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}}
.hring-col{{display:flex;flex-direction:column;align-items:center;gap:4px;width:56px}}
.hring{{background:none;border:none;padding:0;cursor:pointer;line-height:0}}
.hring-name{{font-size:9px;color:{MUTE};text-align:center;line-height:1.2;max-width:56px;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.heat{{display:flex;flex-direction:column;gap:6px}}
.hrow{{display:flex;align-items:center;gap:10px}}
.hname{{flex:0 0 150px;font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
 display:flex;align-items:center}}
.hgrid{{display:flex;gap:{GAP}px;flex-wrap:nowrap;overflow-x:auto}}
.cell{{width:{CELL}px;height:{CELL}px;border:1px solid {RULE};flex:0 0 auto;cursor:pointer}}
.hstreak{{flex:0 0 32px;font-size:10px;color:{SIGNAL};text-align:right;font-variant-numeric:tabular-nums}}
.corr li{{display:flex;gap:9px;padding:6px 0;border-bottom:1px solid {RULE};font-size:12.5px}}
.corr li b{{flex:0 0 150px;display:flex;align-items:center}}
.corr li.dim span{{color:{MUTE};font-style:italic}}
.devo{{border:2px solid {INK};background:{FIELD};padding:14px 16px;margin-bottom:4px}}
.devo.done{{border-color:{SUCCESS}}}
.devo h2{{margin-bottom:9px}}
.moodform{{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;margin-top:10px}}
.moodform label{{display:flex;flex-direction:column;gap:4px;font-size:10px;color:{MUTE};
 text-transform:uppercase;letter-spacing:.06em}}
.moodform input,.moodform select,.jform textarea,.jform input{{font:12.5px 'IBM Plex Mono',monospace;
 background:{FIELD};border:1px solid {RULE};padding:6px 8px;color:{INK}}}
.moodform button,.jform button,.devo button{{font:10.5px 'IBM Plex Sans Condensed',sans-serif;
 letter-spacing:.08em;text-transform:uppercase;background:{INK};color:{FIELD};border:none;
 padding:7px 14px;cursor:pointer}}
.jform{{display:flex;flex-direction:column;gap:10px;margin-top:10px}}
.jform .p{{display:flex;flex-direction:column;gap:5px}}
.jform .p label{{font-size:11.5px;color:{MUTE}}}
.jform textarea{{min-height:56px;width:100%}}
.chips{{display:flex;gap:8px;flex-wrap:wrap}}
.chips button{{background:{FIELD};border:1px solid {RULE};font-size:10.5px;letter-spacing:.06em;
 text-transform:uppercase;padding:5px 10px;cursor:pointer}}
"""


def devotions_block(done_today: bool, streak: int) -> str:
    cls = "devo done" if done_today else "devo"
    if done_today:
        body = f'<p class="sub ok">Logged today · {streak}d streak</p>'
    else:
        body = f"""<form hx-post="/reflect/devotions" hx-target="closest .devo" hx-swap="outerHTML">
<div class="moodform">
<label>Passage<input type="text" name="passage" placeholder="e.g. John 3"></label>
<label>Note<input type="text" name="note"></label>
<button type="submit">Log devotions</button></div></form>
<p class="sub">{streak}d streak</p>"""
    return f'<div class="{cls}"><h2>Devotions</h2>{body}</div>'


def mood_form(today_logged: bool) -> str:
    if today_logged:
        return '<p class="sub ok">Logged today.</p>'
    return """<form class="moodform" hx-post="/reflect/mood" hx-target="closest section" hx-swap="none">
<label>Mood (1-5)<input type="number" name="mood" min="1" max="5" required></label>
<label>Energy (1-5)<input type="number" name="energy" min="1" max="5" required></label>
<label>Tag<input type="text" name="tag" placeholder="one word"></label>
<label>Note<input type="text" name="note"></label>
<button type="submit">Log</button></form>"""


def journal_form(prompts: list[dict]) -> str:
    fields = "".join(f"""<div class="p"><label>{esc(p['text'])}</label>
<textarea name="p{p['id']}"></textarea></div>""" for p in prompts)
    return f"""<form class="jform" hx-post="/reflect/journal" hx-target="this" hx-swap="outerHTML">
{fields}<button type="submit">Save entry</button></form>"""


def render_reflect(state: dict) -> str:
    from .render import CSS as BASE_CSS
    d = date.today()
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reflect</title>
{NO_FLASH_SCRIPT}
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;500;600&display=swap" rel="stylesheet">
<style>{BASE_CSS}{CSS_EXTRA}</style></head><body>
{nav_bar('reflect')}
<div class="wrap">
<header><h1>Reflect</h1><div class="dtg">as of {d.strftime('%a %d %b')}</div></header>

{devotions_block(state['devotions_done_today'], state['devotions_streak'])}

<div class="grid" style="grid-template-columns:1fr">
<section><h2>Mood &amp; energy</h2>{state['mood_chart']}{mood_form(state['mood_logged_today'])}</section>
<section><h2>Habits</h2>{state['habit_rings']}{state['heatmap']}</section>
<section><h2>Quadrant mix — last 6 weeks</h2>{quadrant_chart(state['quadrant_weekly'])}</section>
<section><h2>What tends to move with what</h2>{state['correlation']}</section>
<section><h2>Journal</h2>{journal_form(state['journal_prompts'])}</section>
</div>
</div>
{THEME_TOGGLE_TAG}
</body></html>"""
