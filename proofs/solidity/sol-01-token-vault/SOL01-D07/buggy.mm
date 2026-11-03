struct Payout {
    ok: bool,
    owed: i64,
}

atom _payFee(fee_paid: bool, fee: i64) -> Payout
    requires: fee >= 0;
    ensures: result.ok => (fee == 0 || fee_paid);
    body: {
        Payout { ok: true, owed: (if fee_paid { 0 } else { fee }) }
    }
