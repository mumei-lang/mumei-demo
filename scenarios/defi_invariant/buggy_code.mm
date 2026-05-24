// DeFi Invariant - buggy implementation
// ERC-20 transfer updates the receiver balance without proving the Uint256
// upper bound, so a wrapped/overflowing balance can be admitted.

type Uint256 = i64 where v >= 0 && v <= 100;

atom checked_uint256(value: Uint256)
    requires: value >= 0 && value <= 100;
    ensures: result == value;
    body: {
        value
    };

atom safe_transfer(
    from_balance: Uint256,
    to_balance: i64,
    amount: Uint256
)
    requires: from_balance >= amount && to_balance >= 0 && amount >= 0;
    ensures: result >= 0 && result <= 100;
    body: {
        checked_uint256(to_balance + amount)
    };
