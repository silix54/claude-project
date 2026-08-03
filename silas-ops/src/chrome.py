"""Shared page chrome: color tokens (as CSS custom properties), the nav
bar present on every authenticated page, and dark-mode wiring — system
preference by default, a manual toggle that overrides it and persists in
localStorage, no flash of the wrong theme on load.

Every render_*.py module imports its palette names (FIELD, INK, SIGNAL,
ALERT, MUTE, RULE, plus the new SURFACE and SUCCESS) from here — as CSS
custom-property references, not literal hex. That means every existing
`{INK}`, `{FIELD}` etc. interpolation already scattered across those
files' CSS strings becomes theme-aware for free; no other file needs to
change to support dark mode, and no new colors get introduced independent
of this one palette.

Contrast, checked, not eyeballed: every text/background pairing below was
run through the WCAG 2.1 relative-luminance contrast formula. Light mode
reuses the app's original hex values except --text-muted (#6E7278 was
3.88:1 against the page background, short of AA's 4.5:1 for normal text —
darkened to #61646A, 4.76:1, same hue, still reads as "muted"). Dark mode
derives every value from that same light palette: --bg reuses light
--text as-is, --surface/--border lighten it for card separation, --text
reuses light --bg, and the accent colors are each blended toward that
same off-white — no independently-invented dark colors. Status/text-grade
colors (--signal/--alert/--success/--amber) hold >=4.5:1 against both the
page and card backgrounds; the five --habit-* identity colors are
decorative (rings, heatmap cells, swatches, never body text), checked to
the lower >=3:1 WCAG 1.4.11 non-text/graphical-object threshold instead.

Two separate color systems live here, deliberately not sharing hues:
--signal/--alert/--amber/--text-muted are quadrant/status colors (what
state something is in — urgent, informational, low-priority). The five
--habit-* colors are identity colors (which habit this is — arbitrary,
cycled by creation order, unrelated to any status). Keep them visually
distinct at the call site too: don't recolor quadrant pills with a habit
color or vice versa.
"""

from __future__ import annotations

FIELD = "var(--bg)"
SURFACE = "var(--surface)"
INK = "var(--text)"
MUTE = "var(--text-muted)"
RULE = "var(--border)"
SIGNAL = "var(--signal)"
ALERT = "var(--alert)"
SUCCESS = "var(--success)"
AMBER = "var(--amber)"

HABIT_COLOR_NAMES = ["violet", "teal", "rose", "ochre", "slate"]
HABIT_COLORS = {name: f"var(--habit-{name})" for name in HABIT_COLOR_NAMES}

# Shared by the /plan Eisenhower matrix and the /reflect quadrant-mix
# chart, so both read as one system rather than two features that happen
# to both touch quadrants.
QUADRANT_COLORS = {"now": ALERT, "plan": SIGNAL, "quick": AMBER, "drop": MUTE, "none": MUTE}
QUADRANT_LABELS = {"now": "Now", "plan": "Plan", "quick": "Quick", "drop": "Drop", "none": "Unsorted"}

THEME_VARS = """
:root {
  --bg: #E8E6E1;
  --surface: #F4F2F0;
  --border: #C9C5BC;
  --text: #16181D;
  --text-muted: #61646A;
  --signal: #1F4B99;
  --alert: #A8431C;
  --success: #146B39;
  --amber: #855E0F;
  --habit-violet: #6834B2;
  --habit-teal: #2A928A;
  --habit-rose: #B82E5C;
  --habit-ochre: #6D8F1E;
  --habit-slate: #5A718C;
}
:root[data-theme="dark"] {
  --bg: #16181D;
  --surface: #2B2D31;
  --border: #787774;
  --text: #E8E6E1;
  --text-muted: #999B9D;
  --signal: #7F95BC;
  --alert: #C7917B;
  --success: #7AA68A;
  --amber: #AB925F;
  --habit-violet: #8E69C0;
  --habit-teal: #63ABA4;
  --habit-rose: #C66584;
  --habit-ochre: #92A958;
  --habit-slate: #8594A6;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #16181D;
    --surface: #2B2D31;
    --border: #787774;
    --text: #E8E6E1;
    --text-muted: #999B9D;
    --signal: #7F95BC;
    --alert: #C7917B;
    --success: #7AA68A;
    --amber: #AB925F;
    --habit-violet: #8E69C0;
    --habit-teal: #63ABA4;
    --habit-rose: #C66584;
    --habit-ochre: #92A958;
    --habit-slate: #8594A6;
  }
}
"""

# Runs synchronously in <head>, before <style> is even parsed, so the
# very first paint already has the right theme. An external/deferred
# script running after load would show a flash of the wrong theme first.
NO_FLASH_SCRIPT = """<script>(function(){try{var t=localStorage.getItem('theme');
if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);
}catch(e){}})();</script>"""

THEME_TOGGLE_TAG = '<script src="/static/theme.js"></script>'

# (path, key, label, svg-inner-markup). Hand-drawn line icons, viewBox
# 0 0 20 20, stroke=currentColor — matches the "no chart libraries, hand-
# built SVG" convention already established for the day-bar and mood
# chart, rather than pulling in an icon font or library for four glyphs.
NAV_ITEMS = [
    ("/", "daily", "Today",
     '<circle cx="10" cy="10" r="3.4"/>'
     '<path d="M10,1.6 L10,4 M10,16 L10,18.4 M1.6,10 L4,10 M16,10 L18.4,10 '
     'M4.2,4.2 L5.8,5.8 M14.2,14.2 L15.8,15.8 M4.2,15.8 L5.8,14.2 M14.2,5.8 L15.8,4.2"/>'),
    ("/plan", "plan", "Plan",
     '<rect x="2" y="3.3" width="3" height="3"/><path d="M7.5,4.8 L18,4.8"/>'
     '<rect x="2" y="8.5" width="3" height="3"/><path d="M7.5,10 L18,10"/>'
     '<rect x="2" y="13.7" width="3" height="3"/><path d="M7.5,15.2 L18,15.2"/>'),
    ("/reflect", "reflect", "Reflect",
     '<path d="M1.6,11 L6,11 L7.6,5 L10.6,16 L12.6,8 L14,11 L18.4,11"/>'),
    ("/settings", "settings", "Settings",
     '<path d="M2,5.5 L18,5.5"/><circle cx="12.5" cy="5.5" r="2"/>'
     '<path d="M2,10 L18,10"/><circle cx="7" cy="10" r="2"/>'
     '<path d="M2,14.5 L18,14.5"/><circle cx="13.5" cy="14.5" r="2"/>'),
]

_ICON_WRAP = ('<svg viewBox="0 0 20 20" width="20" height="20" fill="none" '
             'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true">{inner}</svg>')

_TOGGLE_ICON = ('<svg viewBox="0 0 20 20" width="18" height="18" fill="none" '
               'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
               'aria-hidden="true"><circle cx="10" cy="10" r="4"/>'
               '<path d="M10,1.6 L10,3.4 M10,16.6 L10,18.4 M1.6,10 L3.4,10 M16.6,10 L18.4,10 '
               'M4.2,4.2 L5.4,5.4 M14.6,14.6 L15.8,15.8 M4.2,15.8 L5.4,14.6 M14.6,5.4 L15.8,4.2"/></svg>')


def nav_bar(active: str) -> str:
    rows = []
    for href, key, label, inner in NAV_ITEMS:
        is_active = key == active
        cls = "navlink active" if is_active else "navlink"
        current = ' aria-current="page"' if is_active else ""
        rows.append(f'<a href="{href}" class="{cls}"{current}>'
                    f'{_ICON_WRAP.format(inner=inner)}<span>{label}</span></a>')
    links = "".join(rows)
    return (f'<nav class="topnav" aria-label="Primary">{links}'
           f'<button type="button" class="navtoggle" id="theme-toggle" '
           f'onclick="toggleTheme()" aria-label="Toggle dark mode">{_TOGGLE_ICON}</button>'
           f'</nav>')


NAV_CSS = f"""
body{{padding-bottom:74px}}
.topnav{{position:fixed;bottom:0;left:0;right:0;display:flex;align-items:stretch;
 background:{SURFACE};border-top:1px solid {RULE};z-index:50;
 padding-bottom:env(safe-area-inset-bottom)}}
.navlink{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
 gap:2px;padding:8px 2px 7px;color:{MUTE};text-decoration:none;font-size:9.5px;
 letter-spacing:.05em;text-transform:uppercase;font-family:'IBM Plex Sans Condensed',sans-serif}}
.navlink.active{{color:{SIGNAL}}}
.navtoggle{{flex:0 0 52px;display:flex;align-items:center;justify-content:center;
 background:none;border:none;border-left:1px solid {RULE};color:{MUTE};cursor:pointer;padding:0}}
.navtoggle:hover{{color:{SIGNAL}}}
@media(min-width:720px){{
  body{{padding-bottom:60px}}
  .topnav{{position:static;justify-content:flex-start;gap:4px;border-top:none;
   border-bottom:1px solid {RULE};background:{SURFACE};margin-bottom:22px}}
  .navlink{{flex:0 0 auto;flex-direction:row;gap:7px;padding:12px 16px;font-size:11px}}
  .navtoggle{{margin-left:auto;flex:0 0 46px;border-left:1px solid {RULE}}}
}}
"""
