atom withdraw(pending: i64) -> i64
    requires: pending > 0;
    ensures: result == 0;
    body: {
        let at_call = pending;
        at_call
    }
