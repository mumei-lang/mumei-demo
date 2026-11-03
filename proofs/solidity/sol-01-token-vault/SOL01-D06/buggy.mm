atom setWithdrawFeeBps(sender_is_owner: bool, origin_is_owner: bool, bps: i64, max_fee: i64, current: i64) -> i64
    requires: max_fee >= 0;
    ensures: sender_is_owner == false => result == current;
    body: {
        if origin_is_owner && bps <= max_fee { bps } else { current }
    }
