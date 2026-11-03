atom is_over_budget(spent_cents: i64, limit_cents: i64) -> bool
    requires: true;
    ensures: result == (spent_cents >= limit_cents);
    body: {
        spent_cents > limit_cents
    }
