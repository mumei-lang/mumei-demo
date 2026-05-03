// ✅ 正しい RTGS Settlement Protocol 実装

effect Settlement
    states: [Pending, Validated, Settled];
    initial: Pending;
    transition validate: Pending -> Validated;
    transition settle: Validated -> Settled;
    transition reject: Pending -> Pending;

resource ledger priority: 1 mode: exclusive;
resource queue  priority: 2 mode: exclusive;

atom validate_transaction(sender_balance: i64, amount: i64)
    effects: [Settlement];
    effect_pre: { Settlement: Pending };
    effect_post: { Settlement: Validated };
    requires: sender_balance >= 0 && amount > 0 && sender_balance >= amount;
    ensures: result == sender_balance - amount;
    body: {
        perform Settlement.validate;
        sender_balance - amount
    };

atom execute_settlement(sender_balance: i64, receiver_balance: i64, amount: i64)
    effects: [Settlement];
    effect_pre: { Settlement: Validated };
    effect_post: { Settlement: Settled };
    requires: sender_balance >= 0 && receiver_balance >= 0 && amount > 0 && sender_balance >= amount;
    ensures: result == sender_balance + receiver_balance;
    body: {
        perform Settlement.settle;
        let new_sender = sender_balance - amount;
        let new_receiver = receiver_balance + amount;
        new_sender + new_receiver
    };

atom safe_settlement(sender_balance: i64, receiver_balance: i64, amount: i64)
    effects: [Settlement];
    effect_pre: { Settlement: Pending };
    effect_post: { Settlement: Settled };
    requires: sender_balance >= 0 && receiver_balance >= 0 && amount > 0 && sender_balance >= amount;
    ensures: result == sender_balance + receiver_balance;
    body: {
        validate_transaction(sender_balance, amount);
        execute_settlement(sender_balance, receiver_balance, amount)
    };

atom full_settlement(sender_balance: i64, receiver_balance: i64, amount: i64)
    effects: [Settlement];
    effect_pre: { Settlement: Pending };
    effect_post: { Settlement: Settled };
    resources: [ledger, queue];
    requires: sender_balance >= 0 && receiver_balance >= 0 && amount > 0 && sender_balance >= amount;
    ensures: result == sender_balance + receiver_balance;
    body: {
        acquire ledger {
            acquire queue {
                validate_transaction(sender_balance, amount);
                execute_settlement(sender_balance, receiver_balance, amount)
            }
        }
    };
