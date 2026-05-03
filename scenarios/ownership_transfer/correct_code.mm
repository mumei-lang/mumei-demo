// ✅ 正しい Ownership Transfer Protocol 実装

effect Ownership
    states: [Idle, PendingTransfer, Transferred];
    initial: Idle;
    transition propose: Idle -> PendingTransfer;
    transition accept: PendingTransfer -> Transferred;
    transition cancel: PendingTransfer -> Idle;

atom propose_transfer(new_owner: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: PendingTransfer };
    requires: new_owner >= 0;
    ensures: result == new_owner;
    body: {
        perform Ownership.propose;
        new_owner
    };

atom accept_transfer(new_owner: i64)
    effects: [Ownership];
    effect_pre: { Ownership: PendingTransfer };
    effect_post: { Ownership: Transferred };
    requires: new_owner >= 0;
    ensures: result == new_owner;
    body: {
        perform Ownership.accept;
        new_owner
    };

atom cancel_transfer(current_owner: i64)
    effects: [Ownership];
    effect_pre: { Ownership: PendingTransfer };
    effect_post: { Ownership: Idle };
    requires: current_owner >= 0;
    ensures: result == current_owner;
    body: {
        perform Ownership.cancel;
        current_owner
    };

atom full_transfer(new_owner: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: Transferred };
    requires: new_owner >= 0;
    ensures: result == new_owner;
    body: {
        propose_transfer(new_owner);
        accept_transfer(new_owner);
        new_owner
    };

atom propose_and_cancel(owner: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: Idle };
    requires: owner >= 0;
    ensures: result == owner;
    body: {
        propose_transfer(owner);
        cancel_transfer(owner);
        owner
    };
