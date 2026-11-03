atom notifyRewardAmount(is_owner: bool, duration: i64) -> bool
    requires: duration >= 0;
    ensures: is_owner == false => result == false;
    body: {
        if is_owner == false { false } else { duration > 0 }
    }
