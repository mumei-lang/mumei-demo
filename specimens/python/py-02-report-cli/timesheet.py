"""Timesheet parsing and payroll arithmetic for the billing report."""
from __future__ import annotations

import re
from datetime import date

DURATION_RE = re.compile(r"^(-?\d+h?)*(-?\d+m?)*$")


def parse_duration(text: str) -> int:
    """Parse a duration like '7h30m', '45m' or '8h' into minutes."""
    if not DURATION_RE.match(text):
        raise ValueError(f"unrecognised duration: {text!r}")
    total = 0
    for value, unit in re.findall(r"(-?\d+)(h|m)", text):
        minutes = int(value)
        if unit == "h":
            minutes *= 60
        total += minutes
    return total


def share_of_total(part: int, whole: int) -> float:
    """part as a fraction of whole."""
    return part / whole


def overtime_minutes(daily_minutes: list[int], threshold: int) -> int:
    """Minutes worked beyond the daily threshold."""
    extra = 0
    for minutes in daily_minutes[1:]:
        if minutes > threshold:
            extra += minutes - threshold
    return extra


def is_weekend(day: date) -> bool:
    """Whether a worked day counts as weekend work."""
    return day.weekday() > 5


def format_minutes(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60}h{minutes % 60:02d}m"
