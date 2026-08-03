"""Turns habit logs and mood/energy logs into the numbers the reflect view
shows. No numpy — this is small enough that pure Python is clearer and it
keeps the dependency list at just pyyaml.

Design stance, worth stating plainly because it shapes every function here:
this reads your own 1-5 self-ratings, not your journal text. The journal
stays unparsed and unanalyzed, on purpose — it's the one part of this
system that should never become input to an algorithm. Mood and energy are
separate, deliberately lightweight, structured fields exactly so a real
correlation can be computed without ever touching what you wrote in prose.

Every function below gates on sample size and returns confidence=False
below MIN_N. A correlation from eight data points is noise wearing a
number, and this is a personal reflection tool, not a lab, so it should
say "not enough data yet" instead of asserting a pattern that isn't real.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, pstdev

MIN_N = 14  # fewer paired days than this, and we say so instead of guessing


@dataclass
class HabitMoodLink:
    habit: str
    n_with: int
    n_without: int
    mood_with: float | None
    mood_without: float | None
    energy_with: float | None
    energy_without: float | None
    r_mood: float | None       # Pearson r, habit-done (0/1) vs mood
    r_energy: float | None
    confident: bool

    @property
    def mood_delta(self):
        if self.mood_with is None or self.mood_without is None:
            return None
        return round(self.mood_with - self.mood_without, 2)

    @property
    def energy_delta(self):
        if self.energy_with is None or self.energy_without is None:
            return None
        return round(self.energy_with - self.energy_without, 2)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 2)


def habit_mood_link(habit_name: str, habit_days: dict[str, bool],
                    mood_rows: list[dict]) -> HabitMoodLink:
    """habit_days: {iso_date: True} for days the habit was logged done. A
    habit tracker only ever records a positive check, so absence from this
    dict means 'not done', not 'unknown'. Joins against every date that has
    a mood entry, since that is the full universe of comparable days."""
    with_m, with_e, without_m, without_e = [], [], [], []
    xs, ys_mood, ys_energy = [], [], []
    for m in mood_rows:
        if m.get("mood") is None:
            continue
        done = bool(habit_days.get(m["date"], False))
        xs.append(1.0 if done else 0.0)
        ys_mood.append(float(m["mood"]))
        ys_energy.append(float(m["energy"]))
        (with_m if done else without_m).append(m["mood"])
        (with_e if done else without_e).append(m["energy"])

    n_with, n_without = len(with_m), len(without_m)
    confident = (n_with + n_without) >= MIN_N and n_with >= 3 and n_without >= 3

    return HabitMoodLink(
        habit=habit_name, n_with=n_with, n_without=n_without,
        mood_with=round(mean(with_m), 2) if with_m else None,
        mood_without=round(mean(without_m), 2) if without_m else None,
        energy_with=round(mean(with_e), 2) if with_e else None,
        energy_without=round(mean(without_e), 2) if without_e else None,
        r_mood=_pearson(xs, ys_mood) if confident else None,
        r_energy=_pearson(xs, ys_energy) if confident else None,
        confident=confident,
    )


def rolling_stability(mood_rows: list[dict], window: int = 14) -> list[dict]:
    """Population stdev of mood over a trailing window, per day. Lower means
    steadier; this is the operational meaning of 'stability' here — not a
    clinical claim, just the day-to-day spread of your own 1-5 rating."""
    rows = sorted(mood_rows, key=lambda r: r["date"])
    out = []
    for i, r in enumerate(rows):
        window_vals = [x["mood"] for x in rows[max(0, i - window + 1):i + 1]
                       if x.get("mood") is not None]
        sd = round(pstdev(window_vals), 2) if len(window_vals) >= 3 else None
        out.append({"date": r["date"], "mood": r.get("mood"),
                    "energy": r.get("energy"), "stability": sd})
    return out


def all_links(habits: list[dict], mood_rows: list[dict], since: date,
             log_fn) -> list[HabitMoodLink]:
    """habits: rows from db.list_habits(). log_fn: db.habit_logs(id, since)."""
    return [habit_mood_link(h["name"], log_fn(h["id"], since), mood_rows)
            for h in habits]
