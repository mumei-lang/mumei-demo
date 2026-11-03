struct Parsed {
    ok: bool,
    value: i64,
}

atom applyDiscount(amount: i64, percent: i64) -> Parsed
    requires: amount >= 0;
    ensures: result.ok => (result.value >= 0 && result.value <= amount);
    body: {
        if !(percent >= 0 && percent <= 100) { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: amount - amount * percent / 100 } }
    }
