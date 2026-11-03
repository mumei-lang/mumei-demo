struct Parsed {
    ok: bool,
    value: i64,
}

atom invert2x2(a: i64, b: i64, c: i64, d: i64) -> Parsed
    requires: true;
    ensures: result.ok => a * d - b * c != 0;
    body: {
        Parsed { ok: true, value: d / (a * d - b * c) }
    }
