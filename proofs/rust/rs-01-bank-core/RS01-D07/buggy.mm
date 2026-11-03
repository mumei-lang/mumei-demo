atom close_account(queued: i64) -> bool
    requires: queued >= 0;
    ensures: result => queued == 0;
    body: {
        true
    }
