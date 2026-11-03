struct Parsed {
    ok: bool,
    value: i64,
}

atom scale(v: i64, factor: i64) -> Parsed
    requires: v >= (0 - 2147483648) && v <= 2147483647 && factor >= (0 - 2147483648) && factor <= 2147483647;
    ensures: result.ok => (result.value >= (0 - 2147483648) && result.value <= 2147483647);
    body: {
        if v * factor > 2147483647 || v * factor < (0 - 2147483648) { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: v * factor } }
    }
