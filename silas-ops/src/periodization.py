"""Training cycle math. Everything derives from one anchor date in training.yaml."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class CycleState:
    block: int          # 1-indexed block number since anchor
    week_in_block: int  # 1-indexed week within the block
    is_deload: bool
    week_start: date
    week_end: date
    cycle_len: int

    @property
    def label(self) -> str:
        if self.block == 0:
            return "Pre-term"
        if self.is_deload:
            return f"Block {self.block} · deload"
        return f"Block {self.block} · week {self.week_in_block} of {self.cycle_len - 1}"


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def cycle_state(today: date, anchor: date, build_weeks: int = 3,
                deload_weeks: int = 1) -> CycleState:
    """Where `today` sits in the build/deload rhythm.

    Weeks before the anchor return block 0 and are never deload.
    """
    cycle_len = build_weeks + deload_weeks
    ws = monday_of(today)
    anchor_ws = monday_of(anchor)
    weeks_elapsed = (ws - anchor_ws).days // 7

    if weeks_elapsed < 0:
        return CycleState(0, 0, False, ws, ws + timedelta(days=6), cycle_len)

    block = weeks_elapsed // cycle_len + 1
    week_in_block = weeks_elapsed % cycle_len + 1
    is_deload = week_in_block > build_weeks

    return CycleState(block, week_in_block, is_deload, ws,
                      ws + timedelta(days=6), cycle_len)


def upcoming_deloads(anchor: date, through: date, build_weeks: int = 3,
                     deload_weeks: int = 1, start: date | None = None) -> list[date]:
    """Monday of every deload week between `start` and `through`."""
    start = start or date.today()
    out, ws = [], monday_of(start)
    while ws <= through:
        st = cycle_state(ws, anchor, build_weeks, deload_weeks)
        if st.is_deload:
            out.append(ws)
        ws += timedelta(days=7)
    return out


def days_until(target: date, today: date | None = None) -> int:
    return (target - (today or date.today())).days
