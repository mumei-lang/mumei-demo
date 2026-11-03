struct Parsed {
    ok: bool,
    value: i64,
}

atom pick(n: i64, i: i64) -> i64
    requires: 0 <= i && i < n;
    ensures: result == i;
    body: { i }

atom account_at(accounts: i64, index: i64) -> Parsed
    requires: accounts >= 0 && index >= 0;
    ensures: result.ok => index < accounts;
    body: {
        Parsed { ok: true, value: pick(accounts, index) }
    }
