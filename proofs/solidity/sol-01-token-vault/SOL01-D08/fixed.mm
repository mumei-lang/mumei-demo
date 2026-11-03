struct Parsed {
    ok: bool,
    value: i64,
}

atom deposit(pos_shares: i64, shares: i64, cap: i64) -> Parsed
    requires: cap > 0 && pos_shares >= 0 && pos_shares <= cap && shares >= 0;
    ensures: result.ok => (result.value == pos_shares + shares && result.value <= cap);
    body: {
        if shares > cap { Parsed { ok: false, value: 0 } } else { if pos_shares + shares > cap { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: pos_shares + shares } } }
    }
