atom remaining_daily_allowance(limit_cents: i64, spent_cents: i64) -> i64
    requires: limit_cents >= 0 && spent_cents >= 0;
    ensures: result >= 0 && (spent_cents <= limit_cents => result == limit_cents - spent_cents);
    body: {
        if spent_cents > limit_cents { 0 } else { limit_cents - spent_cents }
    }
