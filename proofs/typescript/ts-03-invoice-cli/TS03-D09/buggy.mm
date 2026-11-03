struct Parsed {
    ok: bool,
    value: i64,
}

atom applyDiscount(amount: i64, percent: i64) -> Parsed
    requires: amount >= 0;
    ensures: result.ok => (result.value >= 0 && result.value <= amount);
    body: {
        Parsed { ok: true, value: amount - amount * percent / 100 }
    }
