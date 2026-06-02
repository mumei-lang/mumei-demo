// Blockchain audit scenario - corrected smart contract logic.
//
// The corrected implementation uses Checks-Effects-Interactions, bounded
// Uint256 arithmetic, and explicit owner-only access control contracts.

type Uint256 = i64 where v >= 0 && v <= 100;

effect ReentrancyGuard
    states: [Unlocked, Locked];
    initial: Unlocked;
    transition lock: Unlocked -> Locked;
    transition unlock: Locked -> Unlocked;
    transition call: Locked -> Locked;

atom external_call(user: i64, amount: i64)
    effects: [ReentrancyGuard];
    effect_pre: { ReentrancyGuard: Locked };
    effect_post: { ReentrancyGuard: Locked };
    requires: user >= 0 && amount > 0;
    ensures: result == 0;
    body: {
        perform ReentrancyGuard.call;
        0
    };

atom withdraw(user: i64, balance: i64, amount: i64)
    effects: [ReentrancyGuard];
    effect_pre: { ReentrancyGuard: Unlocked };
    effect_post: { ReentrancyGuard: Unlocked };
    requires: user >= 0 && amount > 0 && balance >= amount;
    ensures: result == balance - amount;
    body: {
        perform ReentrancyGuard.lock;
        let updated_balance = balance - amount;
        external_call(user, amount);
        perform ReentrancyGuard.unlock;
        updated_balance
    };

atom checked_uint256(value: Uint256)
    requires: value >= 0 && value <= 100;
    ensures: result == value;
    body: {
        value
    };

atom safe_credit(
    to_balance: Uint256,
    amount: Uint256
)
    requires: to_balance + amount <= 100;
    ensures: result >= 0 && result <= 100;
    ensures: result == to_balance + amount;
    body: {
        checked_uint256(to_balance + amount)
    };

atom require_owner(caller: i64, owner: i64)
    requires: caller == owner;
    ensures: result == owner;
    body: {
        owner
    };

atom transfer_ownership(caller: i64, owner: i64, new_owner: i64)
    requires: caller >= 0 && owner >= 0 && new_owner >= 0;
    requires: caller == owner;
    ensures: result == new_owner;
    body: {
        require_owner(caller, owner);
        new_owner
    };
