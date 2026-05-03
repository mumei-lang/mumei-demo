// ❌ LLM が生成したバグ入りコード
// validate なしに settle を実行し、Settled へ遷移しようとする
// → 残高検証をスキップした不正決済

effect Settlement
    states: [Pending, Validated, Settled];
    initial: Pending;
    transition validate: Pending -> Validated;
    transition settle: Validated -> Settled;
    transition reject: Pending -> Pending;

atom hostile_settlement(sender_balance: i64, receiver_balance: i64, amount: i64)
    effects: [Settlement];
    effect_pre: { Settlement: Pending };
    effect_post: { Settlement: Settled };
    requires: sender_balance >= 0 && receiver_balance >= 0 && amount > 0;
    ensures: result == sender_balance + receiver_balance;
    body: {
        // BUG: validate をスキップして直接 settle
        // 残高検証なしに決済を実行 — 残高不足でも通ってしまう
        perform Settlement.settle;
        let new_sender = sender_balance - amount;
        let new_receiver = receiver_balance + amount;
        new_sender + new_receiver
    };
