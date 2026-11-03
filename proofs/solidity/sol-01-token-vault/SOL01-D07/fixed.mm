struct Payout {
    ok: bool,
    owed: i64,
}

atom _payFee(fee_paid: bool, fee: i64) -> Payout
    requires: fee >= 0;
    ensures: result.ok => (fee == 0 || fee_paid);
    body: {
        if fee == 0 { Payout { ok: true, owed: 0 } } else { if fee_paid { Payout { ok: true, owed: 0 } } else { Payout { ok: false, owed: fee } } }
    }
