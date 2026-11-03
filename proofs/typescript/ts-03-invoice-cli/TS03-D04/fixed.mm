struct Parsed {
    ok: bool,
    value: i64,
}

atom parseItem(quantity: i64) -> Parsed
    requires: true;
    ensures: result.ok => result.value > 0;
    body: {
        if quantity <= 0 { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: quantity } }
    }
