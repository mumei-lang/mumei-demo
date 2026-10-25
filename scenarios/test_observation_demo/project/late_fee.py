def late_fee(days_late: int, daily_rate: int) -> int:
    if days_late < 0:
        raise ValueError("days_late must be non-negative")
    return days_late * daily_rate
