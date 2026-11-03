atom rewardPerToken(rate: i64, supply: i64, stored: i64, dt: i64) -> i64
    requires: rate >= 0 && supply >= 0 && stored >= 0 && dt >= 0;
    ensures: supply == 0 => result == stored;
    body: {
        if rate == 0 { stored } else { stored + dt * rate / supply * 1000000000000000000 }
    }
