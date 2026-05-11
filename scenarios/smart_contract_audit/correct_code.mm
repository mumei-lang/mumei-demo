// Checks-Effects-Interactions パターンで修正した withdraw 実装

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
