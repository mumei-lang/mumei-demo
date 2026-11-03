struct Payout {
    ok: bool,
    owed: i64,
}

atom getReward(transfer_ok: bool, amount: i64) -> Payout
    requires: amount >= 0;
    ensures: result.ok => transfer_ok;
    body: {
        if transfer_ok { Payout { ok: true, owed: 0 } } else { Payout { ok: false, owed: amount } }
    }
