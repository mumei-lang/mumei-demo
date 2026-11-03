atom sharePrice(total_assets: i64, total_shares: i64) -> i64
    requires: total_assets >= 0 && total_shares >= 0;
    ensures: total_shares == 0 => result == 1000000000000000000;
    body: {
        total_assets * 1000000000000000000 / total_shares
    }
