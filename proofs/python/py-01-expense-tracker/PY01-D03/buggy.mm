atom daily_average(total_cents: i64, days: i64) -> i64
    requires: total_cents >= 0;
    ensures: (days <= 0 => result == 0) && (days > 0 => result == total_cents / days);
    body: {
        total_cents / days
    }
