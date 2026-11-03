struct Queued {
    ok: bool,
    spent: i64,
}

atom request_transfer(balance: i64, queued: i64, limit: i64, spent: i64, amount: i64) -> Queued
    requires: limit >= 0 && spent >= 0 && queued >= 0;
    ensures: result.ok => amount > 0;
    body: {
        if amount <= 0 { Queued { ok: false, spent: spent } }
        else { if balance - queued < amount { Queued { ok: false, spent: spent } }
        else { if amount > (if spent > limit { 0 } else { limit - spent }) { Queued { ok: false, spent: spent } }
        else { Queued { ok: true, spent: spent + amount } } } }
    }
