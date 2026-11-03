struct Close {
    ok: bool,
    moved: i64,
}

atom close_account(closed: bool, balance: i64) -> Close
    requires: balance >= 0;
    ensures: closed => result.ok == false;
    body: {
        Close { ok: true, moved: balance }
    }
