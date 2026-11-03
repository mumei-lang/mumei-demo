atom emergencyWithdraw(balance: i64) -> i64
    requires: balance > 0;
    ensures: result == 0;
    body: {
        let at_call = balance;
        at_call
    }
