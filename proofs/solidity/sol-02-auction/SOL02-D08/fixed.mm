struct Parsed {
    ok: bool,
    value: i64,
}

atom init(now: i64, duration: i64, max_duration: i64, cap: i64) -> Parsed
    requires: cap > 0 && now >= 0 && duration >= 0 && max_duration > 0 && now + max_duration <= cap;
    ensures: result.ok => (result.value >= now && result.value <= cap);
    body: {
        if duration > 0 && duration <= max_duration { Parsed { ok: true, value: now + duration } } else { Parsed { ok: false, value: 0 } }
    }
