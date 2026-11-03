struct Parsed {
    ok: bool,
    value: i64,
}

atom mean(cells: i64, sum: i64) -> Parsed
    requires: cells >= 0;
    ensures: result.ok => cells > 0;
    body: {
        if cells == 0 { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: sum / cells } }
    }
