# sol-03-staking-rewards

Reward-per-token staking pool. Two contracts:

- `src/StakeToken.sol` — minimal ERC20-style token that returns `false` on
  insufficient balance (instead of reverting), plus an opt-in ERC777-style
  receive hook (`setReceiveHook`) delivered via
  `ITokenReceiver.onTokenReceived`.
- `src/StakingRewards.sol` — the pool:
  - `stake(amount)` / `withdraw(amount)` with a 7-day lockup on top-ups and
    `emergencyWithdraw()` for a forfeit-rewards fast exit.
  - Reward accounting: `notifyRewardAmount(reward, duration)`,
    `rewardPerToken()`, `earned(account)`, `getReward()`.
  - Payout routing: `setPayoutAddress(addr)` + `claimFor(user)` settles a
    user's rewards to their configured address.
  - `claimBonus(amount, v, r, s)` redeems operator-signed bonus vouchers.

## Build and test

```bash
export PATH="$HOME/.foundry/bin:$PATH"
forge build
forge test -vv
```

## Scripts

- `./run.sh` — builds and runs the happy-path suite (`HappyPath`).
- `./repro.sh` — runs one test per defect in `DEFECTS.json` and prints
  `[REPRODUCED]`/`[NOT REPRODUCED]` lines.
