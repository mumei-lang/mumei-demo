# sol-01-token-vault

An ERC20-style token plus an ETH vault that mints pro-rata shares, charges a
withdraw fee, and periodically distributes ETH rewards to recorded holders.

## Contracts

- `src/VaultToken.sol` — minimal ERC20 (`balanceOf`, `allowance`,
  `transfer`, `approve`, `transferFrom`, owner `mint`).
- `src/RewardVault.sol` — ETH vault:
  - `deposit()` payable mints shares at the current price
    (`previewDeposit`, `sharePrice`, `totalAssets`, `sharesOf`).
  - `withdraw(shares)` burns shares, takes `withdrawFeeBps` off the payout
    and forwards the fee to `feeRecipient`, and also settles any accrued
    rewards.
  - `distributeRewards()` payable (owner) credits each recorded holder
    pro-rata; `claimRewards()` pays accrued rewards out.
  - Admin: `setFeeRecipient`, `setWithdrawFeeBps`, `pause`, `unpause`.

## Build and test

```bash
export PATH="$HOME/.foundry/bin:$PATH"
forge build
forge test -vv
```

## Scripts

- `./run.sh` — builds and runs the happy-path test suite (`HappyPath`).
- `./repro.sh` — builds once, then runs one focused test per defect listed
  in `DEFECTS.json` and prints `[REPRODUCED]`/`[NOT REPRODUCED]` lines.
