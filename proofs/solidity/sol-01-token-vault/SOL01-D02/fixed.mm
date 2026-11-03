struct Parsed {
    ok: bool,
    value: i64,
}

atom transferFrom(allowed: i64, amount: i64) -> Parsed
    requires: allowed >= 0 && amount >= 0;
    ensures: result.ok => (result.value >= 0 && result.value == allowed - amount);
    body: {
        if allowed >= amount { Parsed { ok: true, value: allowed - amount } } else { Parsed { ok: false, value: 0 } }
    }
