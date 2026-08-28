// Ownership transfer at operational scale: escrowed, quorum-approved,
// time-locked handover over an eight-state temporal effect machine.
// Priority 16 large-scale case: authority, escrow accounting and the final
// "ownership moves exactly once" invariant are all discharged atom-locally.

type Party = i64 where v >= 0 && v <= 1000000;
type Deposit = i64 where v >= 0 && v <= 1000000;
type Flag = i64 where v >= 0 && v <= 1;

effect Ownership
    states: [
        Idle,
        Proposed,
        Acknowledged,
        Escrowed,
        Approved,
        Transferred,
        Recorded,
        Disputed
    ];
    initial: Idle;
    transition propose: Idle -> Proposed;
    transition acknowledge: Proposed -> Acknowledged;
    transition escrow: Acknowledged -> Escrowed;
    transition approve: Escrowed -> Approved;
    transition transfer: Approved -> Transferred;
    transition record: Transferred -> Recorded;
    transition close: Recorded -> Idle;
    transition cancel: Proposed -> Idle;
    transition dispute: Escrowed -> Disputed;
    transition resolve: Disputed -> Idle;

// ---------------------------------------------------------------------------
// Layer 0: escrow arithmetic
// ---------------------------------------------------------------------------

atom floor_zero(value: i64)
    requires: value >= -1000000 && value <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == 0 || result == value;
    body: {
        if value < 0 { 0 } else { value }
    };

atom min_deposit(left: i64, right: i64)
    requires: left >= 0 && left <= 1000000;
    requires: right >= 0 && right <= 1000000;
    ensures: result >= 0;
    ensures: result <= left;
    ensures: result <= right;
    body: {
        if left <= right { left } else { right }
    };

atom escrow_debit(balance: Deposit, amount: Deposit)
    requires: balance >= 0 && balance <= 1000000;
    requires: amount >= 0 && amount <= 1000000;
    requires: balance >= amount;
    ensures: result >= 0;
    ensures: result <= balance;
    ensures: result == balance - amount;
    body: {
        balance - amount
    };

atom escrow_credit(balance: Deposit, amount: Deposit)
    requires: balance >= 0 && balance <= 500000;
    requires: amount >= 0 && amount <= 500000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == balance + amount;
    body: {
        balance + amount
    };

atom transfer_fee(amount: Deposit)
    requires: amount >= 0 && amount <= 1000000;
    ensures: result >= 0;
    ensures: result <= amount;
    body: {
        amount / 200
    };

// ---------------------------------------------------------------------------
// Layer 1: authority predicates
// ---------------------------------------------------------------------------

atom is_current_owner(caller: Party, owner: Party)
    requires: caller >= 0 && caller <= 1000000;
    requires: owner >= 0 && owner <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || caller == owner;
    body: {
        if caller == owner { 1 } else { 0 }
    };

atom recipient_distinct(owner: Party, recipient: Party)
    requires: owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || owner != recipient;
    body: {
        if owner == recipient { 0 } else { 1 }
    };

atom recipient_eligible(recipient_state: i64)
    requires: recipient_state >= 0 && recipient_state <= 3;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || recipient_state == 1;
    body: {
        if recipient_state == 1 { 1 } else { 0 }
    };

atom not_blacklisted(blacklist_hits: i64)
    requires: blacklist_hits >= 0 && blacklist_hits <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || blacklist_hits == 0;
    body: {
        if blacklist_hits == 0 { 1 } else { 0 }
    };

atom quorum_reached(approvals: i64, required: i64)
    requires: approvals >= 0 && approvals <= 100;
    requires: required >= 0 && required <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || approvals >= required;
    body: {
        if approvals >= required { 1 } else { 0 }
    };

atom timelock_elapsed(blocks_since_proposal: i64, timelock_blocks: i64)
    requires: blocks_since_proposal >= 0 && blocks_since_proposal <= 100000;
    requires: timelock_blocks >= 0 && timelock_blocks <= 100000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || blocks_since_proposal >= timelock_blocks;
    body: {
        if blocks_since_proposal >= timelock_blocks { 1 } else { 0 }
    };

atom no_open_dispute(open_disputes: i64)
    requires: open_disputes >= 0 && open_disputes <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || open_disputes == 0;
    body: {
        if open_disputes == 0 { 1 } else { 0 }
    };

atom escrow_funded(escrow_balance: Deposit, required_deposit: Deposit)
    requires: escrow_balance >= 0 && escrow_balance <= 1000000;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || escrow_balance >= required_deposit;
    body: {
        if escrow_balance >= required_deposit { 1 } else { 0 }
    };

atom conjunction(left: Flag, right: Flag)
    requires: left >= 0 && left <= 1;
    requires: right >= 0 && right <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || left == 1;
    ensures: result == 0 || right == 1;
    body: {
        if left == 1 && right == 1 { 1 } else { 0 }
    };

atom conjunction_of_four(first: Flag, second: Flag, third: Flag, fourth: Flag)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1;
    requires: third >= 0 && third <= 1 && fourth >= 0 && fourth <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || first == 1;
    ensures: result == 0 || second == 1;
    ensures: result == 0 || third == 1;
    ensures: result == 0 || fourth == 1;
    body: {
        conjunction(conjunction(first, second), conjunction(third, fourth))
    };

// ---------------------------------------------------------------------------
// Layer 2: composite authority checks
// ---------------------------------------------------------------------------

atom proposal_authorised(caller: Party, owner: Party, recipient: Party, blacklist_hits: i64)
    requires: caller >= 0 && caller <= 1000000 && owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    requires: blacklist_hits >= 0 && blacklist_hits <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || caller == owner;
    body: {
        conjunction(
            conjunction(
                is_current_owner(caller, owner),
                recipient_distinct(owner, recipient)
            ),
            not_blacklisted(blacklist_hits)
        )
    };

atom handover_authorised(
    approvals: i64,
    required: i64,
    blocks_since_proposal: i64,
    timelock_blocks: i64,
    open_disputes: i64,
    escrow_balance: Deposit,
    required_deposit: Deposit
)
    requires: approvals >= 0 && approvals <= 100 && required >= 0 && required <= 100;
    requires: blocks_since_proposal >= 0 && blocks_since_proposal <= 100000;
    requires: timelock_blocks >= 0 && timelock_blocks <= 100000;
    requires: open_disputes >= 0 && open_disputes <= 100;
    requires: escrow_balance >= 0 && escrow_balance <= 1000000;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || approvals >= required;
    ensures: result == 0 || open_disputes == 0;
    body: {
        conjunction_of_four(
            quorum_reached(approvals, required),
            timelock_elapsed(blocks_since_proposal, timelock_blocks),
            no_open_dispute(open_disputes),
            escrow_funded(escrow_balance, required_deposit)
        )
    };

atom settled_deposit(escrow_balance: Deposit, required_deposit: Deposit)
    requires: escrow_balance >= 0 && escrow_balance <= 1000000;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0;
    ensures: result <= escrow_balance;
    ensures: result <= required_deposit;
    body: {
        min_deposit(escrow_balance, required_deposit)
    };

atom owner_after_transfer(authorised: Flag, owner: i64, recipient: i64)
    requires: authorised >= 0 && authorised <= 1;
    requires: owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == owner || result == recipient;
    ensures: authorised == 1 || result == owner;
    body: {
        if authorised == 1 { recipient } else { owner }
    };

// ---------------------------------------------------------------------------
// Layer 3: effectful handover stages
// ---------------------------------------------------------------------------

atom stage_propose(caller: Party, owner: Party, recipient: Party, blacklist_hits: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: Proposed };
    requires: caller >= 0 && caller <= 1000000 && owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    requires: blacklist_hits >= 0 && blacklist_hits <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || caller == owner;
    body: {
        perform Ownership.propose;
        proposal_authorised(caller, owner, recipient, blacklist_hits)
    };

atom stage_acknowledge(proposal_ok: Flag, recipient_state: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Proposed };
    effect_post: { Ownership: Acknowledged };
    requires: proposal_ok >= 0 && proposal_ok <= 1;
    requires: recipient_state >= 0 && recipient_state <= 3;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || proposal_ok == 1;
    ensures: result == 0 || recipient_state == 1;
    body: {
        perform Ownership.acknowledge;
        conjunction(proposal_ok, recipient_eligible(recipient_state))
    };

atom stage_escrow(escrow_balance: Deposit, deposit_amount: Deposit)
    effects: [Ownership];
    effect_pre: { Ownership: Acknowledged };
    effect_post: { Ownership: Escrowed };
    requires: escrow_balance >= 0 && escrow_balance <= 500000;
    requires: deposit_amount >= 0 && deposit_amount <= 500000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == escrow_balance + deposit_amount;
    body: {
        perform Ownership.escrow;
        escrow_credit(escrow_balance, deposit_amount)
    };

atom stage_approve(
    approvals: i64,
    required: i64,
    blocks_since_proposal: i64,
    timelock_blocks: i64,
    open_disputes: i64,
    escrow_balance: Deposit,
    required_deposit: Deposit
)
    effects: [Ownership];
    effect_pre: { Ownership: Escrowed };
    effect_post: { Ownership: Approved };
    requires: approvals >= 0 && approvals <= 100 && required >= 0 && required <= 100;
    requires: blocks_since_proposal >= 0 && blocks_since_proposal <= 100000;
    requires: timelock_blocks >= 0 && timelock_blocks <= 100000;
    requires: open_disputes >= 0 && open_disputes <= 100;
    requires: escrow_balance >= 0 && escrow_balance <= 1000000;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || approvals >= required;
    body: {
        perform Ownership.approve;
        handover_authorised(
            approvals,
            required,
            blocks_since_proposal,
            timelock_blocks,
            open_disputes,
            escrow_balance,
            required_deposit
        )
    };

atom stage_transfer(authorised: Flag, owner: Party, recipient: Party)
    effects: [Ownership];
    effect_pre: { Ownership: Approved };
    effect_post: { Ownership: Transferred };
    requires: authorised >= 0 && authorised <= 1;
    requires: owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == owner || result == recipient;
    ensures: authorised == 1 || result == owner;
    body: {
        perform Ownership.transfer;
        owner_after_transfer(authorised, owner, recipient)
    };

atom stage_record(new_owner: Party, escrow_balance: Deposit, released: Deposit)
    effects: [Ownership];
    effect_pre: { Ownership: Transferred };
    effect_post: { Ownership: Recorded };
    requires: new_owner >= 0 && new_owner <= 1000000;
    requires: escrow_balance >= 0 && escrow_balance <= 1000000;
    requires: released >= 0 && released <= 1000000;
    requires: escrow_balance >= released;
    ensures: result >= 0;
    ensures: result <= escrow_balance;
    ensures: result == escrow_balance - released;
    body: {
        perform Ownership.record;
        escrow_debit(escrow_balance, released)
    };

atom stage_close(remaining_escrow: Deposit)
    effects: [Ownership];
    effect_pre: { Ownership: Recorded };
    effect_post: { Ownership: Idle };
    requires: remaining_escrow >= 0 && remaining_escrow <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == remaining_escrow;
    body: {
        perform Ownership.close;
        remaining_escrow
    };

atom stage_cancel(owner: Party)
    effects: [Ownership];
    effect_pre: { Ownership: Proposed };
    effect_post: { Ownership: Idle };
    requires: owner >= 0 && owner <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == owner;
    body: {
        perform Ownership.cancel;
        owner
    };

atom stage_dispute(open_disputes: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Escrowed };
    effect_post: { Ownership: Disputed };
    requires: open_disputes >= 0 && open_disputes <= 99;
    ensures: result >= 1;
    ensures: result == open_disputes + 1;
    body: {
        perform Ownership.dispute;
        open_disputes + 1
    };

atom stage_resolve(open_disputes: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Disputed };
    effect_post: { Ownership: Idle };
    requires: open_disputes >= 1 && open_disputes <= 100;
    ensures: result >= 0;
    ensures: result == open_disputes - 1;
    body: {
        perform Ownership.resolve;
        open_disputes - 1
    };

// ---------------------------------------------------------------------------
// Layer 4: phases
// ---------------------------------------------------------------------------

atom phase_initiate(
    caller: Party,
    owner: Party,
    recipient: Party,
    blacklist_hits: i64,
    recipient_state: i64
)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: Acknowledged };
    requires: caller >= 0 && caller <= 1000000 && owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    requires: blacklist_hits >= 0 && blacklist_hits <= 100;
    requires: recipient_state >= 0 && recipient_state <= 3;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || recipient_state == 1;
    body: {
        let proposal_ok = stage_propose(caller, owner, recipient, blacklist_hits);
        stage_acknowledge(proposal_ok, recipient_state)
    };

atom phase_secure(
    escrow_balance: Deposit,
    deposit_amount: Deposit,
    approvals: i64,
    required: i64,
    blocks_since_proposal: i64,
    timelock_blocks: i64,
    open_disputes: i64,
    required_deposit: Deposit
)
    effects: [Ownership];
    effect_pre: { Ownership: Acknowledged };
    effect_post: { Ownership: Approved };
    requires: escrow_balance >= 0 && escrow_balance <= 500000;
    requires: deposit_amount >= 0 && deposit_amount <= 500000;
    requires: approvals >= 0 && approvals <= 100 && required >= 0 && required <= 100;
    requires: blocks_since_proposal >= 0 && blocks_since_proposal <= 100000;
    requires: timelock_blocks >= 0 && timelock_blocks <= 100000;
    requires: open_disputes >= 0 && open_disputes <= 100;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || approvals >= required;
    body: {
        let funded = stage_escrow(escrow_balance, deposit_amount);
        stage_approve(
            approvals,
            required,
            blocks_since_proposal,
            timelock_blocks,
            open_disputes,
            funded,
            required_deposit
        )
    };

atom phase_hand_over(
    authorised: Flag,
    owner: Party,
    recipient: Party,
    escrow_balance: Deposit,
    required_deposit: Deposit
)
    effects: [Ownership];
    effect_pre: { Ownership: Approved };
    effect_post: { Ownership: Idle };
    requires: authorised >= 0 && authorised <= 1;
    requires: owner >= 0 && owner <= 1000000 && recipient >= 0 && recipient <= 1000000;
    requires: escrow_balance >= 0 && escrow_balance <= 1000000;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result <= escrow_balance;
    body: {
        let new_owner = stage_transfer(authorised, owner, recipient);
        let released = settled_deposit(escrow_balance, required_deposit);
        let remaining = stage_record(new_owner, escrow_balance, released);
        stage_close(remaining)
    };

atom phase_dispute_and_resolve(open_disputes: i64)
    effects: [Ownership];
    effect_pre: { Ownership: Escrowed };
    effect_post: { Ownership: Idle };
    requires: open_disputes >= 0 && open_disputes <= 99;
    ensures: result >= 0;
    ensures: result == open_disputes;
    body: {
        let raised = stage_dispute(open_disputes);
        stage_resolve(raised)
    };

// ---------------------------------------------------------------------------
// Layer 5: whole handover flows
// ---------------------------------------------------------------------------

atom handover_cycle(
    caller: Party,
    owner: Party,
    recipient: Party,
    blacklist_hits: i64,
    recipient_state: i64,
    escrow_balance: Deposit,
    deposit_amount: Deposit,
    approvals: i64,
    required: i64,
    blocks_since_proposal: i64,
    timelock_blocks: i64,
    open_disputes: i64,
    required_deposit: Deposit
)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: Idle };
    requires: caller >= 0 && caller <= 1000000 && owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    requires: blacklist_hits >= 0 && blacklist_hits <= 100;
    requires: recipient_state >= 0 && recipient_state <= 3;
    requires: escrow_balance >= 0 && escrow_balance <= 500000;
    requires: deposit_amount >= 0 && deposit_amount <= 500000;
    requires: approvals >= 0 && approvals <= 100 && required >= 0 && required <= 100;
    requires: blocks_since_proposal >= 0 && blocks_since_proposal <= 100000;
    requires: timelock_blocks >= 0 && timelock_blocks <= 100000;
    requires: open_disputes >= 0 && open_disputes <= 100;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    body: {
        phase_initiate(caller, owner, recipient, blacklist_hits, recipient_state);
        let authorised = phase_secure(
            escrow_balance,
            deposit_amount,
            approvals,
            required,
            blocks_since_proposal,
            timelock_blocks,
            open_disputes,
            required_deposit
        );
        let funded = escrow_credit(escrow_balance, deposit_amount);
        phase_hand_over(authorised, owner, recipient, funded, required_deposit)
    };

atom two_handover_cycles(
    caller: Party,
    owner: Party,
    recipient: Party,
    blacklist_hits: i64,
    recipient_state: i64,
    escrow_balance: Deposit,
    deposit_amount: Deposit,
    approvals: i64,
    required: i64,
    blocks_since_proposal: i64,
    timelock_blocks: i64,
    open_disputes: i64,
    required_deposit: Deposit
)
    effects: [Ownership];
    effect_pre: { Ownership: Idle };
    effect_post: { Ownership: Idle };
    requires: caller >= 0 && caller <= 1000000 && owner >= 0 && owner <= 1000000;
    requires: recipient >= 0 && recipient <= 1000000;
    requires: blacklist_hits >= 0 && blacklist_hits <= 100;
    requires: recipient_state >= 0 && recipient_state <= 3;
    requires: escrow_balance >= 0 && escrow_balance <= 500000;
    requires: deposit_amount >= 0 && deposit_amount <= 500000;
    requires: approvals >= 0 && approvals <= 100 && required >= 0 && required <= 100;
    requires: blocks_since_proposal >= 0 && blocks_since_proposal <= 100000;
    requires: timelock_blocks >= 0 && timelock_blocks <= 100000;
    requires: open_disputes >= 0 && open_disputes <= 100;
    requires: required_deposit >= 0 && required_deposit <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    body: {
        handover_cycle(
            caller,
            owner,
            recipient,
            blacklist_hits,
            recipient_state,
            escrow_balance,
            deposit_amount,
            approvals,
            required,
            blocks_since_proposal,
            timelock_blocks,
            open_disputes,
            required_deposit
        );
        handover_cycle(
            caller,
            owner,
            recipient,
            blacklist_hits,
            recipient_state,
            escrow_balance,
            deposit_amount,
            approvals,
            required,
            blocks_since_proposal,
            timelock_blocks,
            open_disputes,
            required_deposit
        )
    };
