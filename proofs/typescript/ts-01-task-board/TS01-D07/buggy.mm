struct Parsed {
    ok: bool,
    value: i64,
}

atom parsePriority(missing: bool, numeric: bool, value: i64) -> Parsed
    requires: true;
    ensures: result.ok => (result.value >= 1 && result.value <= 5);
    body: {
        if missing { Parsed { ok: true, value: 3 } }
        else { if numeric && (value < 1 || value > 5) { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: value } } }
    }
