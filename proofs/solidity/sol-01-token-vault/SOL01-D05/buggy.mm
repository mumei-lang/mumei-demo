atom setFeeRecipient(is_owner: bool, who: i64, current: i64) -> i64
    requires: true;
    ensures: is_owner == false => result == current;
    body: {
        who
    }
