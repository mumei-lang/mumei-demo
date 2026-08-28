// RTGS settlement at operational scale: submission -> finality -> reconciliation.
// Priority 16 large-scale case: settlement finality and balance conservation are
// chained across an eight-state temporal effect machine. Every composite stage
// closes with the ensures of its callees only — no global ledger invariant is
// assumed anywhere in the pipeline.

type Amount = i64 where v >= 0 && v <= 1000000;
type Balance = i64 where v >= 0 && v <= 2000000;

effect Settlement
    states: [
        Idle,
        Submitted,
        Validated,
        Reserved,
        Netted,
        Posted,
        Finalized,
        Reconciled
    ];
    initial: Idle;
    transition submit: Idle -> Submitted;
    transition validate: Submitted -> Validated;
    transition reserve: Validated -> Reserved;
    transition net: Reserved -> Netted;
    transition post: Netted -> Posted;
    transition finalize: Posted -> Finalized;
    transition reconcile: Finalized -> Reconciled;
    transition close: Reconciled -> Idle;
    transition reject: Submitted -> Idle;
    transition unwind: Reserved -> Idle;

// ---------------------------------------------------------------------------
// Layer 0: pure ledger arithmetic
// ---------------------------------------------------------------------------

atom non_negative(value: i64)
    requires: value >= -2000000 && value <= 2000000;
    ensures: result >= 0;
    ensures: result <= 2000000;
    ensures: result <= value || result == 0;
    body: {
        if value >= 0 { value } else { 0 }
    };

atom min_amount(left: i64, right: i64)
    requires: left >= 0 && left <= 1000000;
    requires: right >= 0 && right <= 1000000;
    ensures: result >= 0;
    ensures: result <= left;
    ensures: result <= right;
    body: {
        if left <= right { left } else { right }
    };

atom debit_balance(balance: Balance, amount: Amount)
    requires: balance >= 0 && balance <= 2000000;
    requires: amount >= 0 && amount <= 1000000;
    requires: balance >= amount;
    ensures: result >= 0;
    ensures: result <= balance;
    ensures: result == balance - amount;
    body: {
        balance - amount
    };

atom credit_balance(balance: Balance, amount: Amount)
    requires: balance >= 0 && balance <= 1000000;
    requires: amount >= 0 && amount <= 1000000;
    ensures: result >= 0;
    ensures: result <= 2000000;
    ensures: result == balance + amount;
    body: {
        balance + amount
    };

atom conserved_total(sender_after: Balance, receiver_after: Balance)
    requires: sender_after >= 0 && sender_after <= 2000000;
    requires: receiver_after >= 0 && receiver_after <= 2000000;
    ensures: result >= 0;
    ensures: result == sender_after + receiver_after;
    body: {
        sender_after + receiver_after
    };

// ---------------------------------------------------------------------------
// Layer 1: pure settlement predicates
// ---------------------------------------------------------------------------

atom amount_in_scheme_limit(amount: Amount, scheme_limit: Amount)
    requires: amount >= 0 && amount <= 1000000;
    requires: scheme_limit >= 0 && scheme_limit <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || amount <= scheme_limit;
    body: {
        if amount <= scheme_limit { 1 } else { 0 }
    };

atom liquidity_available(balance: Balance, amount: Amount)
    requires: balance >= 0 && balance <= 2000000;
    requires: amount >= 0 && amount <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || balance >= amount;
    body: {
        if balance >= amount { 1 } else { 0 }
    };

atom participant_active(status_code: i64)
    requires: status_code >= 0 && status_code <= 3;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || status_code == 1;
    body: {
        if status_code == 1 { 1 } else { 0 }
    };

atom cutoff_not_passed(minutes_to_cutoff: i64)
    requires: minutes_to_cutoff >= -600 && minutes_to_cutoff <= 600;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || minutes_to_cutoff > 0;
    body: {
        if minutes_to_cutoff > 0 { 1 } else { 0 }
    };

atom both_hold(first: i64, second: i64)
    requires: first >= 0 && first <= 1;
    requires: second >= 0 && second <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || first == 1;
    ensures: result == 0 || second == 1;
    body: {
        if first == 1 { second } else { 0 }
    };

atom all_four_hold(first: i64, second: i64, third: i64, fourth: i64)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1;
    requires: third >= 0 && third <= 1 && fourth >= 0 && fourth <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || first == 1;
    ensures: result == 0 || fourth == 1;
    body: {
        let head = both_hold(first, second);
        let tail = both_hold(third, fourth);
        both_hold(head, tail)
    };

// ---------------------------------------------------------------------------
// Layer 2: pure netting and settlement planning
// ---------------------------------------------------------------------------

atom bilateral_net(outgoing: Amount, incoming: Amount)
    requires: outgoing >= 0 && outgoing <= 1000000;
    requires: incoming >= 0 && incoming <= 1000000;
    ensures: result >= 0;
    ensures: result <= 1000000;
    ensures: result <= outgoing;
    body: {
        non_negative(outgoing - incoming)
    };

atom settleable_amount(balance: Balance, requested: Amount, scheme_limit: Amount)
    requires: balance >= 0 && balance <= 1000000;
    requires: requested >= 0 && requested <= 1000000;
    requires: scheme_limit >= 0 && scheme_limit <= 1000000;
    ensures: result >= 0;
    ensures: result <= requested;
    ensures: result <= balance;
    ensures: result <= scheme_limit;
    body: {
        let capped = min_amount(requested, scheme_limit);
        min_amount(capped, balance)
    };

atom reserved_liquidity(balance: Balance, planned: Amount, buffer: Amount)
    requires: balance >= 0 && balance <= 1000000;
    requires: planned >= 0 && planned <= 1000000;
    requires: buffer >= 0 && buffer <= 1000000;
    ensures: result >= 0;
    ensures: result <= planned;
    ensures: result <= balance;
    body: {
        let usable = non_negative(balance - buffer);
        let bounded = min_amount(usable, 1000000);
        min_amount(planned, bounded)
    };

atom finality_amount(reserved: Amount, netted: Amount)
    requires: reserved >= 0 && reserved <= 1000000;
    requires: netted >= 0 && netted <= 1000000;
    ensures: result >= 0;
    ensures: result <= reserved;
    ensures: result <= netted;
    body: {
        min_amount(reserved, netted)
    };

// ---------------------------------------------------------------------------
// Layer 3: effectful settlement stages
// ---------------------------------------------------------------------------

atom stage_submit(amount: Amount, scheme_limit: Amount)
    effects: [Settlement];
    effect_pre: { Settlement: Idle };
    effect_post: { Settlement: Submitted };
    requires: amount >= 0 && amount <= 1000000;
    requires: scheme_limit >= 0 && scheme_limit <= 1000000;
    ensures: result >= 0 && result <= 1;
    body: {
        perform Settlement.submit;
        amount_in_scheme_limit(amount, scheme_limit)
    };

atom stage_validate(
    sender_status: i64,
    receiver_status: i64,
    minutes_to_cutoff: i64,
    scheme_ok: i64
)
    effects: [Settlement];
    effect_pre: { Settlement: Submitted };
    effect_post: { Settlement: Validated };
    requires: sender_status >= 0 && sender_status <= 3;
    requires: receiver_status >= 0 && receiver_status <= 3;
    requires: minutes_to_cutoff >= -600 && minutes_to_cutoff <= 600;
    requires: scheme_ok >= 0 && scheme_ok <= 1;
    ensures: result >= 0 && result <= 1;
    body: {
        perform Settlement.validate;
        all_four_hold(
            participant_active(sender_status),
            participant_active(receiver_status),
            cutoff_not_passed(minutes_to_cutoff),
            scheme_ok
        )
    };

atom stage_reserve(sender_balance: Balance, requested: Amount, buffer: Amount)
    effects: [Settlement];
    effect_pre: { Settlement: Validated };
    effect_post: { Settlement: Reserved };
    requires: sender_balance >= 0 && sender_balance <= 1000000;
    requires: requested >= 0 && requested <= 1000000;
    requires: buffer >= 0 && buffer <= 1000000;
    ensures: result >= 0;
    ensures: result <= requested;
    ensures: result <= sender_balance;
    body: {
        perform Settlement.reserve;
        reserved_liquidity(sender_balance, requested, buffer)
    };

atom stage_net(reserved: Amount, incoming: Amount)
    effects: [Settlement];
    effect_pre: { Settlement: Reserved };
    effect_post: { Settlement: Netted };
    requires: reserved >= 0 && reserved <= 1000000;
    requires: incoming >= 0 && incoming <= 1000000;
    ensures: result >= 0;
    ensures: result <= reserved;
    body: {
        perform Settlement.net;
        bilateral_net(reserved, incoming)
    };

atom stage_post(sender_balance: Balance, settled: Amount)
    effects: [Settlement];
    effect_pre: { Settlement: Netted };
    effect_post: { Settlement: Posted };
    requires: sender_balance >= 0 && sender_balance <= 2000000;
    requires: settled >= 0 && settled <= 1000000;
    requires: sender_balance >= settled;
    ensures: result >= 0;
    ensures: result <= sender_balance;
    ensures: result == sender_balance - settled;
    body: {
        perform Settlement.post;
        debit_balance(sender_balance, settled)
    };

atom stage_finalize(receiver_balance: Balance, settled: Amount)
    effects: [Settlement];
    effect_pre: { Settlement: Posted };
    effect_post: { Settlement: Finalized };
    requires: receiver_balance >= 0 && receiver_balance <= 1000000;
    requires: settled >= 0 && settled <= 1000000;
    ensures: result >= 0;
    ensures: result <= 2000000;
    ensures: result == receiver_balance + settled;
    body: {
        perform Settlement.finalize;
        credit_balance(receiver_balance, settled)
    };

atom stage_reconcile(sender_after: Balance, receiver_after: Balance)
    effects: [Settlement];
    effect_pre: { Settlement: Finalized };
    effect_post: { Settlement: Reconciled };
    requires: sender_after >= 0 && sender_after <= 2000000;
    requires: receiver_after >= 0 && receiver_after <= 2000000;
    ensures: result >= 0;
    ensures: result == sender_after + receiver_after;
    body: {
        perform Settlement.reconcile;
        conserved_total(sender_after, receiver_after)
    };

atom stage_close(total_after: i64)
    effects: [Settlement];
    effect_pre: { Settlement: Reconciled };
    effect_post: { Settlement: Idle };
    requires: total_after >= 0 && total_after <= 4000000;
    ensures: result >= 0;
    ensures: result == total_after;
    body: {
        perform Settlement.close;
        total_after
    };

// ---------------------------------------------------------------------------
// Layer 4: phases
// ---------------------------------------------------------------------------

atom phase_admit(
    amount: Amount,
    scheme_limit: Amount,
    sender_status: i64,
    receiver_status: i64,
    minutes_to_cutoff: i64
)
    effects: [Settlement];
    effect_pre: { Settlement: Idle };
    effect_post: { Settlement: Validated };
    requires: amount >= 0 && amount <= 1000000;
    requires: scheme_limit >= 0 && scheme_limit <= 1000000;
    requires: sender_status >= 0 && sender_status <= 3;
    requires: receiver_status >= 0 && receiver_status <= 3;
    requires: minutes_to_cutoff >= -600 && minutes_to_cutoff <= 600;
    ensures: result >= 0 && result <= 1;
    body: {
        let scheme_ok = stage_submit(amount, scheme_limit);
        stage_validate(sender_status, receiver_status, minutes_to_cutoff, scheme_ok)
    };

atom phase_reserve_and_net(
    sender_balance: Balance,
    requested: Amount,
    buffer: Amount,
    incoming: Amount
)
    effects: [Settlement];
    effect_pre: { Settlement: Validated };
    effect_post: { Settlement: Netted };
    requires: sender_balance >= 0 && sender_balance <= 1000000;
    requires: requested >= 0 && requested <= 1000000;
    requires: buffer >= 0 && buffer <= 1000000;
    requires: incoming >= 0 && incoming <= 1000000;
    ensures: result >= 0;
    ensures: result <= requested;
    ensures: result <= sender_balance;
    body: {
        let reserved = stage_reserve(sender_balance, requested, buffer);
        stage_net(reserved, incoming)
    };

atom phase_settle(sender_balance: Balance, receiver_balance: Balance, settled: Amount)
    effects: [Settlement];
    effect_pre: { Settlement: Netted };
    effect_post: { Settlement: Finalized };
    requires: sender_balance >= 0 && sender_balance <= 1000000;
    requires: receiver_balance >= 0 && receiver_balance <= 1000000;
    requires: settled >= 0 && settled <= 1000000;
    requires: sender_balance >= settled;
    ensures: result >= 0;
    ensures: result <= 2000000;
    ensures: result == receiver_balance + settled;
    body: {
        stage_post(sender_balance, settled);
        stage_finalize(receiver_balance, settled)
    };

atom phase_wrap_up(sender_after: Balance, receiver_after: Balance)
    effects: [Settlement];
    effect_pre: { Settlement: Finalized };
    effect_post: { Settlement: Idle };
    requires: sender_after >= 0 && sender_after <= 2000000;
    requires: receiver_after >= 0 && receiver_after <= 2000000;
    ensures: result >= 0;
    ensures: result == sender_after + receiver_after;
    body: {
        let total = stage_reconcile(sender_after, receiver_after);
        stage_close(total)
    };

// ---------------------------------------------------------------------------
// Layer 5: whole settlement cycles
// ---------------------------------------------------------------------------

atom settlement_cycle(
    sender_balance: Balance,
    receiver_balance: Balance,
    requested: Amount,
    scheme_limit: Amount,
    buffer: Amount,
    incoming: Amount,
    sender_status: i64,
    receiver_status: i64,
    minutes_to_cutoff: i64
)
    effects: [Settlement];
    effect_pre: { Settlement: Idle };
    effect_post: { Settlement: Idle };
    requires: sender_balance >= 0 && sender_balance <= 1000000;
    requires: receiver_balance >= 0 && receiver_balance <= 1000000;
    requires: requested >= 0 && requested <= 1000000;
    requires: scheme_limit >= 0 && scheme_limit <= 1000000;
    requires: buffer >= 0 && buffer <= 1000000;
    requires: incoming >= 0 && incoming <= 1000000;
    requires: sender_status >= 0 && sender_status <= 3;
    requires: receiver_status >= 0 && receiver_status <= 3;
    requires: minutes_to_cutoff >= -600 && minutes_to_cutoff <= 600;
    ensures: result >= 0;
    ensures: result <= 4000000;
    ensures: result == sender_balance + receiver_balance;
    body: {
        phase_admit(amount_in_window(requested), scheme_limit, sender_status, receiver_status, minutes_to_cutoff);
        let settled = phase_reserve_and_net(sender_balance, requested, buffer, incoming);
        let receiver_after = phase_settle(sender_balance, receiver_balance, settled);
        let sender_after = debit_balance(sender_balance, settled);
        phase_wrap_up(sender_after, receiver_after)
    };

atom amount_in_window(requested: Amount)
    requires: requested >= 0 && requested <= 1000000;
    ensures: result >= 0;
    ensures: result <= 1000000;
    ensures: result == requested;
    body: {
        requested
    };

atom two_settlement_cycles(
    sender_balance: Balance,
    receiver_balance: Balance,
    requested: Amount,
    scheme_limit: Amount,
    buffer: Amount,
    incoming: Amount,
    sender_status: i64,
    receiver_status: i64,
    minutes_to_cutoff: i64
)
    effects: [Settlement];
    effect_pre: { Settlement: Idle };
    effect_post: { Settlement: Idle };
    requires: sender_balance >= 0 && sender_balance <= 1000000;
    requires: receiver_balance >= 0 && receiver_balance <= 1000000;
    requires: requested >= 0 && requested <= 1000000;
    requires: scheme_limit >= 0 && scheme_limit <= 1000000;
    requires: buffer >= 0 && buffer <= 1000000;
    requires: incoming >= 0 && incoming <= 1000000;
    requires: sender_status >= 0 && sender_status <= 3;
    requires: receiver_status >= 0 && receiver_status <= 3;
    requires: minutes_to_cutoff >= -600 && minutes_to_cutoff <= 600;
    ensures: result >= 0;
    ensures: result <= 4000000;
    ensures: result == sender_balance + receiver_balance;
    body: {
        settlement_cycle(
            sender_balance,
            receiver_balance,
            requested,
            scheme_limit,
            buffer,
            incoming,
            sender_status,
            receiver_status,
            minutes_to_cutoff
        );
        settlement_cycle(
            sender_balance,
            receiver_balance,
            requested,
            scheme_limit,
            buffer,
            incoming,
            sender_status,
            receiver_status,
            minutes_to_cutoff
        )
    };
