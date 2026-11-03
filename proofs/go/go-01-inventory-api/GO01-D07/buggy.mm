struct Parsed {
    ok: bool,
    value: i64,
}

atom slice_to(n: i64, end: i64) -> i64
    requires: 0 <= end && end <= n;
    ensures: result == end;
    body: { end }

atom reportHandler(n: i64, has_limit: bool, limit: i64) -> Parsed
    requires: n >= 0;
    ensures: result.ok => (result.value >= 0 && result.value <= n);
    body: {
        Parsed { ok: true, value: slice_to(n, if has_limit { limit } else { n }) }
    }
