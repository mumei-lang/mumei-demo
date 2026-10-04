## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/solidity/sol-03-staking-rewards`
- verification_status: `refuted`
- Summary: Audit directory: specimens/solidity/sol-03-staking-rewards\n  src/StakeToken.sol: 4 violations, 0 gaps\n  src/StakingRewards.sol: 11 violations, 0 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 4 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: onTokenReceived.requires, onTokenReceived.ensures, mint.requires, mint.ensures, setReceiveHook.requires, setReceiveHook.ensures, transfer.requires, transfer.ensures, approve.requires, transferFrom.requires, transferFrom.ensures, move.requires, move.ensures, notifyReceiver.requires, notifyReceiver.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: balanceOf.requires, balanceOf.ensures, transfer.requires, transfer.ensures, transferFrom.requires, transferFrom.ensures, lastTimeRewardApplicable.requires, lastTimeRewardApplicable.ensures, rewardPerToken.requires, rewardPerToken.ensures, earned.ensures, stake.requires, stake.ensures, withdraw.requires, withdraw.ensures, emergencyWithdraw.requires, emergencyWithdraw.ensures, getReward.requires, getReward.ensures, setPayoutAddress.requires, setPayoutAddress.ensures, claimFor.requires, claimFor.ensures, claimBonus.requires, claimBonus.ensures, notifyRewardAmount.requires, notifyRewardAmount.ensures, setOperator.requires, setOperator.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: onTokenReceived.requires, onTokenReceived.ensures, mint.requires, mint.ensures, setReceiveHook.requires, setReceiveHook.ensures, transfer.requires, transfer.ensures, approve.requires, transferFrom.requires, transferFrom.ensures, move.requires, move.ensures, notifyReceiver.requires, notifyReceiver.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: balanceOf.requires, balanceOf.ensures, transfer.requires, transfer.ensures, transferFrom.requires, transferFrom.ensures, lastTimeRewardApplicable.requires, lastTimeRewardApplicable.ensures, rewardPerToken.requires, rewardPerToken.ensures, earned.ensures, stake.requires, stake.ensures, withdraw.requires, withdraw.ensures, emergencyWithdraw.requires, emergencyWithdraw.ensures, getReward.requires, getReward.ensures, setPayoutAddress.requires, setPayoutAddress.ensures, claimFor.requires, claimFor.ensures, claimBonus.requires, claimBonus.ensures, notifyRewardAmount.requires, notifyRewardAmount.ensures, setOperator.requires, setOperator.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["src/StakeToken.sol: Solidity function `mint` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless", "src/StakeToken.sol: Solidity function `setReceiveHook` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless", "src/StakeToken.sol: Solidity function `approve` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless"]

### 検出事項
- `verification_violations`
  - src/StakeToken.sol: Solidity function `mint` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakeToken.sol: Solidity function `setReceiveHook` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakeToken.sol: Solidity function `approve` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakeToken.sol: Solidity function `transferFrom` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakingRewards.sol: Solidity function `earned` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakingRewards.sol: Solidity function `stake` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakingRewards.sol: Solidity function `withdraw` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakingRewards.sol: Solidity function `emergencyWithdraw` may be vulnerable to reentrancy: verified guard-state-machine trace shows an external call reachable in the Unlocked state before a later state write (Checks-Effects-Interactions violation; move state updates before external calls or add a reentrancy guard)
  - src/StakingRewards.sol: Solidity function `emergencyWithdraw` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/StakingRewards.sol: Solidity function `getReward` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
