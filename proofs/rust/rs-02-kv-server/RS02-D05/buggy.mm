struct Parsed {
    ok: bool,
    value: i64,
}

atom incr(current: i64, delta: i64) -> Parsed
    requires: current >= (0 - 2147483648) && current <= 2147483647 && delta >= (0 - 2147483648) && delta <= 2147483647;
    ensures: result.ok => (result.value >= (0 - 2147483648) && result.value <= 2147483647);
    body: {
        Parsed { ok: true, value: current + delta }
    }
