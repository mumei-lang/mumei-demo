atom clicksPerDay(clicks: i64, created_at: i64, now: i64) -> i64
    requires: clicks >= 0 && now >= created_at;
    ensures: result >= 0 && result <= clicks;
    body: {
        clicks / ((now - created_at) / 86400)
    }
