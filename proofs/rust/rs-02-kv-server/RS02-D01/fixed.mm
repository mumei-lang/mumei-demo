struct Parsed {
    ok: bool,
    value: i64,
}

atom pick(n: i64, i: i64) -> i64
    requires: 0 <= i && i < n;
    ensures: result == i;
    body: { i }

atom read_request(words: i64) -> Parsed
    requires: words >= 0;
    ensures: result.ok => words >= 2;
    body: {
        if words < 2 { Parsed { ok: false, value: 0 } } else { let method = pick(words, 0); Parsed { ok: true, value: pick(words, 1) } }
    }
