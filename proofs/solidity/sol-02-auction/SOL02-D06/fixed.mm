atom cancelBid(is_highest: bool, amount: i64) -> bool
    requires: amount >= 0;
    ensures: is_highest == true => result == false;
    body: {
        if is_highest { false } else { amount > 0 }
    }
