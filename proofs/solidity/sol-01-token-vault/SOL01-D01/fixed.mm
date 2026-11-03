atom withdraw(shares_before: i64, shares: i64) -> i64
    requires: shares >= 0 && shares_before >= shares;
    ensures: result == shares_before - shares;
    body: {
        let after = shares_before - shares;
        after
    }
