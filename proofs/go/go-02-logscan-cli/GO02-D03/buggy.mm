struct Parsed {
    ok: bool,
    value: i64,
}

atom slice_to(n: i64, end: i64) -> i64
    requires: 0 <= end && end <= n;
    ensures: result == end;
    body: { end }

atom formatSummary(n_paths: i64, top: i64) -> Parsed
    requires: n_paths >= 0;
    ensures: result.ok => (result.value >= 0 && result.value <= n_paths);
    body: {
        Parsed { ok: true, value: slice_to(n_paths, top) }
    }
