// DeFi Invariant - correct implementation
// Uint256 is represented as a bounded i64 refinement for the demo harness.
// The transfer contract proves both debit sufficiency and receiver overflow safety.

type Uint256 = i64 where v >= 0 && v <= 100;

atom checked_uint256(value: Uint256)
    requires: value >= 0 && value <= 100;
    ensures: result == value;
    body: {
        value
    };

atom safe_transfer(
    from_balance: Uint256,
    to_balance: Uint256,
    amount: Uint256
)
    requires: from_balance >= amount;
    requires: to_balance + amount <= 100;
    ensures: result >= 0 && result <= 100;
    ensures: result == to_balance + amount;
    body: {
        checked_uint256(to_balance + amount)
    };
