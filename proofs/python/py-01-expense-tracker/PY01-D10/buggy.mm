struct Parsed {
    ok: bool,
    value: i64,
}

atom parse_amount(value: i64) -> Parsed
    requires: true;
    ensures: (result.ok => result.value > 0 && result.value == value) && (value > 0 => result.ok);
    body: {
        Parsed { ok: true, value: value }
    }
