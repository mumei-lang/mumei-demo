// Blockchain audit scenario - intentionally vulnerable smart contract logic.
//
// The file groups three common audit findings:
// - reentrancy: external_call is reached without acquiring the guard;
// - integer overflow: receiver balance addition lacks the Uint256 upper bound;
// - access control: privileged ownership transfer lacks caller == owner proof.

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
        let updated_balance = balance - amount;
        external_call(user, amount);
        updated_balance
    };

atom checked_uint256(value: Uint256)
    requires: value >= 0 && value <= 100;
    ensures: result == value;
    body: {
        value
    };

atom credit_without_overflow_proof(
    to_balance: i64,
    amount: Uint256
)
    requires: to_balance >= 0 && amount >= 0;
    ensures: result >= 0 && result <= 100;
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
    ensures: result == new_owner;
    body: {
        require_owner(caller, owner);
        new_owner
    };
