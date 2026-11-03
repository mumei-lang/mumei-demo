struct Parsed {
    ok: bool,
    value: i64,
}

atom parse_duration(hours: i64, minutes: i64) -> Parsed
    requires: true;
    ensures: result.ok => result.value > 0;
    body: {
        Parsed { ok: true, value: hours * 60 + minutes }
    }
