struct Parsed {
    ok: bool,
    value: i64,
}

atom share_expiry(now: i64, ttl_seconds: i64) -> Parsed
    requires: true;
    ensures: result.ok => result.value > now;
    body: {
        Parsed { ok: true, value: now + ttl_seconds }
    }
