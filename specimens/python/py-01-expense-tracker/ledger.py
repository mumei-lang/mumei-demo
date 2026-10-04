"""Pure expense arithmetic shared by the HTTP handlers."""
from __future__ import annotations


def parse_amount(value) -> int:
    """Convert a JSON amount field into integer cents."""
    return int(value)


def daily_average(total_cents: int, days: int) -> int:
    """Average spend per active day in the period."""
    return total_cents // days


def average_expense(amounts: list[int]) -> int:
    """Mean expense size in cents, rounded to a whole cent."""
    return round(sum(amounts) / len(amounts))


def is_over_budget(spent_cents: int, limit_cents: int) -> bool:
    """Whether the month's spend has used up the budget."""
    return spent_cents > limit_cents


def subcategory(label: str) -> str:
    """The part of a category label after the group prefix, e.g. 'food:groceries' -> 'groceries'."""
    return label.split(":")[1]
