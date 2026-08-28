// DeFi vault at operational scale: reentrancy guard, pool solvency and
// ownership handover chained through an eight-state temporal effect machine.
// Priority 16 large-scale case: the pool invariant (reserves never drop below
// the settled outflow, shares never exceed supply) is discharged only from the
// ensures of the immediately called atoms.

type Token = i64 where v >= 0 && v <= 1000000;
type Shares = i64 where v >= 0 && v <= 1000000;
type Flag = i64 where v >= 0 && v <= 1;

effect Vault
    states: [
        Idle,
        Entered,
        Checked,
        Debited,
        Credited,
        Minted,
        Settled,
        Exited
    ];
    initial: Idle;
    transition enter: Idle -> Entered;
    transition check: Entered -> Checked;
    transition debit: Checked -> Debited;
    transition credit: Debited -> Credited;
    transition mint: Credited -> Minted;
    transition settle: Minted -> Settled;
    transition exit_guard: Settled -> Exited;
    transition release: Exited -> Idle;
    transition revert_call: Checked -> Idle;

// ---------------------------------------------------------------------------
// Layer 0: checked arithmetic
// ---------------------------------------------------------------------------

atom clamp_non_negative(value: i64)
    requires: value >= -1000000 && value <= 1000000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == 0 || result == value;
    body: {
        if value < 0 { 0 } else { value }
    };

atom min_token(left: i64, right: i64)
    requires: left >= 0 && left <= 1000000;
    requires: right >= 0 && right <= 1000000;
    ensures: result >= 0;
    ensures: result <= left;
    ensures: result <= right;
    body: {
        if left <= right { left } else { right }
    };

atom checked_sub(balance: Token, amount: Token)
    requires: balance >= 0 && balance <= 1000000;
    requires: amount >= 0 && amount <= 1000000;
    requires: balance >= amount;
    ensures: result >= 0;
    ensures: result <= balance;
    ensures: result == balance - amount;
    body: {
        balance - amount
    };

atom checked_add(balance: Token, amount: Token)
    requires: balance >= 0 && balance <= 500000;
    requires: amount >= 0 && amount <= 500000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == balance + amount;
    body: {
        balance + amount
    };

atom protocol_fee(amount: Token)
    requires: amount >= 0 && amount <= 1000000;
    ensures: result >= 0;
    ensures: result <= amount;
    body: {
        amount / 100
    };

atom net_of_fee(amount: Token, fee: Token)
    requires: amount >= 0 && amount <= 1000000;
    requires: fee >= 0 && fee <= 1000000;
    requires: amount >= fee;
    ensures: result >= 0;
    ensures: result <= amount;
    ensures: result == amount - fee;
    body: {
        amount - fee
    };

// ---------------------------------------------------------------------------
// Layer 1: guard and safety predicates
// ---------------------------------------------------------------------------

atom guard_free(guard_state: Flag)
    requires: guard_state >= 0 && guard_state <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || guard_state == 0;
    body: {
        if guard_state == 0 { 1 } else { 0 }
    };

atom caller_is_owner(caller_id: i64, owner_id: i64)
    requires: caller_id >= 0 && caller_id <= 1000000;
    requires: owner_id >= 0 && owner_id <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || caller_id == owner_id;
    body: {
        if caller_id == owner_id { 1 } else { 0 }
    };

atom allowance_sufficient(allowance: Token, amount: Token)
    requires: allowance >= 0 && allowance <= 1000000;
    requires: amount >= 0 && amount <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || allowance >= amount;
    body: {
        if allowance >= amount { 1 } else { 0 }
    };

atom slippage_within_bound(quoted: Token, minimum_out: Token)
    requires: quoted >= 0 && quoted <= 1000000;
    requires: minimum_out >= 0 && minimum_out <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || quoted >= minimum_out;
    body: {
        if quoted >= minimum_out { 1 } else { 0 }
    };

atom deadline_not_expired(seconds_left: i64)
    requires: seconds_left >= -100000 && seconds_left <= 100000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || seconds_left > 0;
    body: {
        if seconds_left > 0 { 1 } else { 0 }
    };

atom pool_solvent(reserve: Token, outflow: Token)
    requires: reserve >= 0 && reserve <= 1000000;
    requires: outflow >= 0 && outflow <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || reserve >= outflow;
    body: {
        if reserve >= outflow { 1 } else { 0 }
    };

atom both_ok(left: Flag, right: Flag)
    requires: left >= 0 && left <= 1;
    requires: right >= 0 && right <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || left == 1;
    ensures: result == 0 || right == 1;
    body: {
        if left == 1 && right == 1 { 1 } else { 0 }
    };

atom all_five_ok(first: Flag, second: Flag, third: Flag, fourth: Flag, fifth: Flag)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1;
    requires: third >= 0 && third <= 1 && fourth >= 0 && fourth <= 1;
    requires: fifth >= 0 && fifth <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || first == 1;
    ensures: result == 0 || fifth == 1;
    body: {
        let head = both_ok(both_ok(first, second), third);
        both_ok(both_ok(head, fourth), fifth)
    };

// ---------------------------------------------------------------------------
// Layer 2: pool accounting
// ---------------------------------------------------------------------------

atom withdrawable_amount(reserve: Token, requested: Token, user_balance: Token)
    requires: reserve >= 0 && reserve <= 1000000;
    requires: requested >= 0 && requested <= 1000000;
    requires: user_balance >= 0 && user_balance <= 1000000;
    ensures: result >= 0;
    ensures: result <= requested;
    ensures: result <= reserve;
    ensures: result <= user_balance;
    body: {
        min_token(min_token(requested, reserve), user_balance)
    };

atom payout_after_fee(gross: Token)
    requires: gross >= 0 && gross <= 1000000;
    ensures: result >= 0;
    ensures: result <= gross;
    body: {
        net_of_fee(gross, protocol_fee(gross))
    };

atom reserve_after_payout(reserve: Token, payout: Token)
    requires: reserve >= 0 && reserve <= 1000000;
    requires: payout >= 0 && payout <= 1000000;
    requires: reserve >= payout;
    ensures: result >= 0;
    ensures: result <= reserve;
    ensures: result == reserve - payout;
    body: {
        checked_sub(reserve, payout)
    };

atom shares_to_burn(shares_held: Shares, requested: Shares)
    requires: shares_held >= 0 && shares_held <= 1000000;
    requires: requested >= 0 && requested <= 1000000;
    ensures: result >= 0;
    ensures: result <= shares_held;
    ensures: result <= requested;
    body: {
        min_token(shares_held, requested)
    };

atom supply_after_burn(total_supply: Shares, burned: Shares)
    requires: total_supply >= 0 && total_supply <= 1000000;
    requires: burned >= 0 && burned <= 1000000;
    requires: total_supply >= burned;
    ensures: result >= 0;
    ensures: result <= total_supply;
    ensures: result == total_supply - burned;
    body: {
        checked_sub(total_supply, burned)
    };

// ---------------------------------------------------------------------------
// Layer 3: effectful vault stages
// ---------------------------------------------------------------------------

atom stage_enter(guard_state: Flag)
    effects: [Vault];
    effect_pre: { Vault: Idle };
    effect_post: { Vault: Entered };
    requires: guard_state >= 0 && guard_state <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || guard_state == 0;
    body: {
        perform Vault.enter;
        guard_free(guard_state)
    };

atom stage_check(
    entered: Flag,
    caller_id: i64,
    owner_id: i64,
    allowance: Token,
    requested: Token,
    quoted: Token,
    minimum_out: Token,
    seconds_left: i64
)
    effects: [Vault];
    effect_pre: { Vault: Entered };
    effect_post: { Vault: Checked };
    requires: entered >= 0 && entered <= 1;
    requires: caller_id >= 0 && caller_id <= 1000000 && owner_id >= 0 && owner_id <= 1000000;
    requires: allowance >= 0 && allowance <= 1000000 && requested >= 0 && requested <= 1000000;
    requires: quoted >= 0 && quoted <= 1000000 && minimum_out >= 0 && minimum_out <= 1000000;
    requires: seconds_left >= -100000 && seconds_left <= 100000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || entered == 1;
    body: {
        perform Vault.check;
        all_five_ok(
            entered,
            caller_is_owner(caller_id, owner_id),
            allowance_sufficient(allowance, requested),
            slippage_within_bound(quoted, minimum_out),
            deadline_not_expired(seconds_left)
        )
    };

atom stage_debit(reserve: Token, payout: Token)
    effects: [Vault];
    effect_pre: { Vault: Checked };
    effect_post: { Vault: Debited };
    requires: reserve >= 0 && reserve <= 1000000;
    requires: payout >= 0 && payout <= 1000000;
    requires: reserve >= payout;
    ensures: result >= 0;
    ensures: result <= reserve;
    ensures: result == reserve - payout;
    body: {
        perform Vault.debit;
        reserve_after_payout(reserve, payout)
    };

atom stage_credit(user_balance: Token, payout: Token)
    effects: [Vault];
    effect_pre: { Vault: Debited };
    effect_post: { Vault: Credited };
    requires: user_balance >= 0 && user_balance <= 500000;
    requires: payout >= 0 && payout <= 500000;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == user_balance + payout;
    body: {
        perform Vault.credit;
        checked_add(user_balance, payout)
    };

atom stage_mint(total_supply: Shares, burned: Shares)
    effects: [Vault];
    effect_pre: { Vault: Credited };
    effect_post: { Vault: Minted };
    requires: total_supply >= 0 && total_supply <= 1000000;
    requires: burned >= 0 && burned <= 1000000;
    requires: total_supply >= burned;
    ensures: result >= 0;
    ensures: result <= total_supply;
    ensures: result == total_supply - burned;
    body: {
        perform Vault.mint;
        supply_after_burn(total_supply, burned)
    };

atom stage_settle(reserve_after: Token, outflow: Token)
    effects: [Vault];
    effect_pre: { Vault: Minted };
    effect_post: { Vault: Settled };
    requires: reserve_after >= 0 && reserve_after <= 1000000;
    requires: outflow >= 0 && outflow <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || reserve_after >= outflow;
    body: {
        perform Vault.settle;
        pool_solvent(reserve_after, outflow)
    };

atom stage_exit(settled: Flag)
    effects: [Vault];
    effect_pre: { Vault: Settled };
    effect_post: { Vault: Exited };
    requires: settled >= 0 && settled <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == settled;
    body: {
        perform Vault.exit_guard;
        settled
    };

atom stage_release(settled: Flag)
    effects: [Vault];
    effect_pre: { Vault: Exited };
    effect_post: { Vault: Idle };
    requires: settled >= 0 && settled <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == settled;
    body: {
        perform Vault.release;
        settled
    };

// ---------------------------------------------------------------------------
// Layer 4: phases
// ---------------------------------------------------------------------------

atom phase_admit(
    guard_state: Flag,
    caller_id: i64,
    owner_id: i64,
    allowance: Token,
    requested: Token,
    quoted: Token,
    minimum_out: Token,
    seconds_left: i64
)
    effects: [Vault];
    effect_pre: { Vault: Idle };
    effect_post: { Vault: Checked };
    requires: guard_state >= 0 && guard_state <= 1;
    requires: caller_id >= 0 && caller_id <= 1000000 && owner_id >= 0 && owner_id <= 1000000;
    requires: allowance >= 0 && allowance <= 1000000 && requested >= 0 && requested <= 1000000;
    requires: quoted >= 0 && quoted <= 1000000 && minimum_out >= 0 && minimum_out <= 1000000;
    requires: seconds_left >= -100000 && seconds_left <= 100000;
    ensures: result >= 0 && result <= 1;
    body: {
        let entered = stage_enter(guard_state);
        stage_check(
            entered,
            caller_id,
            owner_id,
            allowance,
            requested,
            quoted,
            minimum_out,
            seconds_left
        )
    };

atom phase_move_funds(reserve: Token, user_balance: Token, payout: Token)
    effects: [Vault];
    effect_pre: { Vault: Checked };
    effect_post: { Vault: Credited };
    requires: reserve >= 0 && reserve <= 1000000;
    requires: user_balance >= 0 && user_balance <= 500000;
    requires: payout >= 0 && payout <= 500000;
    requires: reserve >= payout;
    ensures: result >= 0 && result <= 1000000;
    ensures: result == user_balance + payout;
    body: {
        stage_debit(reserve, payout);
        stage_credit(user_balance, payout)
    };

atom phase_close_position(
    total_supply: Shares,
    burned: Shares,
    reserve_after: Token,
    outflow: Token
)
    effects: [Vault];
    effect_pre: { Vault: Credited };
    effect_post: { Vault: Idle };
    requires: total_supply >= 0 && total_supply <= 1000000;
    requires: burned >= 0 && burned <= 1000000;
    requires: total_supply >= burned;
    requires: reserve_after >= 0 && reserve_after <= 1000000;
    requires: outflow >= 0 && outflow <= 1000000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || reserve_after >= outflow;
    body: {
        stage_mint(total_supply, burned);
        let settled = stage_settle(reserve_after, outflow);
        let exited = stage_exit(settled);
        stage_release(exited)
    };

// ---------------------------------------------------------------------------
// Layer 5: whole withdrawal flows
// ---------------------------------------------------------------------------

atom withdrawal_cycle(
    guard_state: Flag,
    caller_id: i64,
    owner_id: i64,
    allowance: Token,
    requested: Token,
    quoted: Token,
    minimum_out: Token,
    seconds_left: i64,
    reserve: Token,
    user_balance: Token,
    shares_held: Shares,
    total_supply: Shares
)
    effects: [Vault];
    effect_pre: { Vault: Idle };
    effect_post: { Vault: Idle };
    requires: guard_state >= 0 && guard_state <= 1;
    requires: caller_id >= 0 && caller_id <= 1000000 && owner_id >= 0 && owner_id <= 1000000;
    requires: allowance >= 0 && allowance <= 1000000 && requested >= 0 && requested <= 500000;
    requires: quoted >= 0 && quoted <= 1000000 && minimum_out >= 0 && minimum_out <= 1000000;
    requires: seconds_left >= -100000 && seconds_left <= 100000;
    requires: reserve >= 0 && reserve <= 500000;
    requires: user_balance >= 0 && user_balance <= 500000;
    requires: shares_held >= 0 && shares_held <= 1000000;
    requires: total_supply >= 0 && total_supply <= 1000000;
    requires: total_supply >= shares_held;
    ensures: result >= 0 && result <= 1;
    body: {
        phase_admit(
            guard_state,
            caller_id,
            owner_id,
            allowance,
            requested,
            quoted,
            minimum_out,
            seconds_left
        );
        let gross = withdrawable_amount(reserve, requested, user_balance);
        let payout = payout_after_fee(gross);
        phase_move_funds(reserve, user_balance, payout);
        let burned = shares_to_burn(shares_held, requested);
        let remaining_reserve = reserve_after_payout(reserve, payout);
        phase_close_position(total_supply, burned, remaining_reserve, 0)
    };

atom two_withdrawal_cycles(
    guard_state: Flag,
    caller_id: i64,
    owner_id: i64,
    allowance: Token,
    requested: Token,
    quoted: Token,
    minimum_out: Token,
    seconds_left: i64,
    reserve: Token,
    user_balance: Token,
    shares_held: Shares,
    total_supply: Shares
)
    effects: [Vault];
    effect_pre: { Vault: Idle };
    effect_post: { Vault: Idle };
    requires: guard_state >= 0 && guard_state <= 1;
    requires: caller_id >= 0 && caller_id <= 1000000 && owner_id >= 0 && owner_id <= 1000000;
    requires: allowance >= 0 && allowance <= 1000000 && requested >= 0 && requested <= 500000;
    requires: quoted >= 0 && quoted <= 1000000 && minimum_out >= 0 && minimum_out <= 1000000;
    requires: seconds_left >= -100000 && seconds_left <= 100000;
    requires: reserve >= 0 && reserve <= 500000;
    requires: user_balance >= 0 && user_balance <= 500000;
    requires: shares_held >= 0 && shares_held <= 1000000;
    requires: total_supply >= 0 && total_supply <= 1000000;
    requires: total_supply >= shares_held;
    ensures: result >= 0 && result <= 1;
    body: {
        withdrawal_cycle(
            guard_state,
            caller_id,
            owner_id,
            allowance,
            requested,
            quoted,
            minimum_out,
            seconds_left,
            reserve,
            user_balance,
            shares_held,
            total_supply
        );
        withdrawal_cycle(
            guard_state,
            caller_id,
            owner_id,
            allowance,
            requested,
            quoted,
            minimum_out,
            seconds_left,
            reserve,
            user_balance,
            shares_held,
            total_supply
        )
    };
