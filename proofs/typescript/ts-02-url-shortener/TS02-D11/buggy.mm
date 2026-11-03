struct Parsed {
    ok: bool,
    value: i64,
}

atom deref(present: bool) -> bool
    requires: present;
    ensures: result;
    body: { true }

atom linkStats(found: bool, clicks: i64) -> Parsed
    requires: true;
    ensures: found == false => result.ok == false;
    body: {
        let touched = deref(found);
        Parsed { ok: true, value: clicks }
    }
