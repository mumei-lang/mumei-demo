struct Parsed {
    ok: bool,
    value: i64,
}

atom parse_row(row: [i64], n: i64) -> Parsed
    requires: len(row) == n && n >= 0;
    ensures: (result.ok => n >= 4) && (n >= 4 => result.ok);
    body: {
        Parsed { ok: true, value: row[3] }
    }
