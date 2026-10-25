atom late_fee(days_late: i64, daily_rate: i64) -> i64 {
    requires: days_late >= 0 && daily_rate >= 0;
    ensures: result == days_late * daily_rate;
    body: {
        days_late * daily_rate
    }
}
