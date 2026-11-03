struct Parsed {
    ok: bool,
    value: i64,
}

atom split_payment(amount_cents: i64, recipients: i64) -> Parsed
    requires: recipients >= 0;
    ensures: result.ok => recipients > 0;
    body: {
        if recipients == 0 { Parsed { ok: false, value: 0 } } else { Parsed { ok: true, value: amount_cents / recipients } }
    }
