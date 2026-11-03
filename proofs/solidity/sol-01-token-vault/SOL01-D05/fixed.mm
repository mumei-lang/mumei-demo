atom setFeeRecipient(is_owner: bool, who: i64, current: i64) -> i64
    requires: true;
    ensures: is_owner == false => result == current;
    body: {
        if is_owner == false { current } else { if who == 0 { current } else { who } }
    }
