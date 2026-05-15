// 航空管制プロトコル - 正しい実装
// 順序付けられたロックと相互排除

effect RunwayAllocation
    states: [Idle, Ordered, Allocated];
    initial: Idle;
    transition order: Idle -> Ordered;
    transition allocate: Ordered -> Allocated;

resource runway_primary priority: 1 mode: exclusive;
resource runway_secondary priority: 2 mode: exclusive;

atom order_runway_locks(
    flight: i64,
    runway1: i64,
    runway2: i64
)
    effects: [RunwayAllocation];
    effect_pre: { RunwayAllocation: Idle };
    effect_post: { RunwayAllocation: Ordered };
    requires: flight >= 0 && runway1 >= 0 && runway2 >= 0 && runway1 < runway2;
    ensures: result == runway1 + runway2;
    body: {
        perform RunwayAllocation.order;
        runway1 + runway2
    };

atom commit_runway_allocation(
    ordered_lock_state: i64,
    runway1: i64,
    runway2: i64
)
    effects: [RunwayAllocation];
    effect_pre: { RunwayAllocation: Ordered };
    effect_post: { RunwayAllocation: Allocated };
    resources: [runway_primary, runway_secondary];
    requires: runway1 >= 0 && runway2 >= 0 && runway1 < runway2;
    requires: ordered_lock_state == runway1 + runway2;
    ensures: result == runway1 + runway2;
    body: {
        acquire runway_primary {
            acquire runway_secondary {
                perform RunwayAllocation.allocate;
                ordered_lock_state
            }
        }
    };

atom allocate_runway(
    flight: i64,
    runway1: i64,
    runway2: i64,
    lock_state: i64
)
    effects: [RunwayAllocation];
    effect_pre: { RunwayAllocation: Idle };
    effect_post: { RunwayAllocation: Allocated };
    resources: [runway_primary, runway_secondary];
    requires: flight >= 0 && runway1 >= 0 && runway2 >= 0 && runway1 != runway2 && runway1 < runway2;
    ensures: result != 0;
    ensures: result == runway1 + runway2;
    body: {
        let ordered_lock_state = order_runway_locks(flight, runway1, runway2);
        commit_runway_allocation(ordered_lock_state, runway1, runway2)
    };
