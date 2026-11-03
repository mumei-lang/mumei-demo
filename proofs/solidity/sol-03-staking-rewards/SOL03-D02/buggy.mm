struct Parsed {
    ok: bool,
    value: i64,
}

atom earned(rpt: i64, paid: i64, bal: i64, rewards: i64) -> Parsed
    requires: rpt >= 0 && paid >= 0 && bal >= 0 && rewards >= 0;
    ensures: result.ok => result.value >= rewards;
    body: {
        Parsed { ok: true, value: rewards + bal * (rpt - paid) / 1000000000000000000 }
    }
