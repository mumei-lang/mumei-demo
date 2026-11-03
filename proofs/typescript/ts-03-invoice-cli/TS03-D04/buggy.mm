struct Parsed {
    ok: bool,
    value: i64,
}

atom parseItem(quantity: i64) -> Parsed
    requires: true;
    ensures: result.ok => result.value > 0;
    body: {
        Parsed { ok: true, value: quantity }
    }
