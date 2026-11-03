struct Fee {
    ok: bool,
    balance: i64,
}

atom charge_fee(balance: i64, cents: i64) -> Fee
    requires: true;
    ensures: result.ok => result.balance < balance;
    body: {
        Fee { ok: true, balance: balance - cents }
    }
