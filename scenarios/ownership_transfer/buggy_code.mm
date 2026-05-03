// ❌ LLM が生成したバグ入りコード
// PendingTransfer なしに accept を実行し、Transferred へ遷移しようとする

effect Ownership
    states: [Idle, PendingTransfer, Transferred];
    initial: Idle;
    transition propose: Idle -> PendingTransfer;
    transition accept: PendingTransfer -> Transferred;
    transition cancel: PendingTransfer -> Idle;

atom hostile_takeover(attacker: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: Transferred };
    requires: attacker >= 0;
    ensures: result == attacker;
    body: {
        perform Ownership.accept;
        attacker
    };
