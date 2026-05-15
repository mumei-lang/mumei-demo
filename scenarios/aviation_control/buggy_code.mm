// 航空管制プロトコル - バグ入り実装
// ロック順序が一貫しておらず、デッドロックの可能性

effect RunwayAllocation
    states: [Idle, Ordered, Allocated];
    initial: Idle;
    transition order: Idle -> Ordered;
    transition allocate: Ordered -> Allocated;

atom allocate_runway(
    flight: i64,
    runway1: i64,
    runway2: i64,
    lock_state: i64
)
    effects: [RunwayAllocation];
    effect_pre: { RunwayAllocation: Idle };
    effect_post: { RunwayAllocation: Allocated };
    requires: flight >= 0 && runway1 >= 0 && runway2 >= 0 && runway1 != runway2;
    ensures: result != 0;
    body: {
        perform RunwayAllocation.allocate;
        runway2
    };
