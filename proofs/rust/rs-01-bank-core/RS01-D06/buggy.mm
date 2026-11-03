struct Queued {
    ok: bool,
    spent: i64,
}

atom request_transfer(balance: i64, queued: i64, limit: i64, spent: i64, amount: i64) -> Queued
    requires: limit >= 0 && spent >= 0 && queued >= 0;
    ensures: result.ok == false => result.spent == spent;
    body: {
        if balance < amount { Queued { ok: false, spent: spent } }
        else { if amount > 0 { if spent <= limit && amount > limit - spent { Queued { ok: false, spent: 0 } } else { Queued { ok: true, spent: spent + amount } } }
        else { Queued { ok: true, spent: spent } } }
    }
