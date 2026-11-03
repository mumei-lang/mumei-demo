struct Parsed {
    ok: bool,
    value: i64,
}

atom parse_duration(hours: i64, minutes: i64) -> Parsed
    requires: true;
    ensures: result.ok => result.value > 0;
    body: {
        if hours < 0 || minutes < 0 { Parsed { ok: false, value: 0 } } else { if hours * 60 + minutes <= 0 { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: hours * 60 + minutes } } }
    }
