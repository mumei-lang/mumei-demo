## No-.mm ディレクトリ監査レポート

- ステータス: **合格**
- 言語: `mixed`
- Source: `specimens/solidity/sol-03-staking-rewards`
- verification_status: `verified`
- finding_counts: `code=0, confirmed=0, spec=0, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `0`
- Summary: Audit directory: specimens/solidity/sol-03-staking-rewards\n  src/StakeToken.sol: 0 violations, 0 gaps\n  src/StakingRewards.sol: 0 violations, 0 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 4 files, 0 files with issues, 0 files with spec diagnostics\nfinding_counts: code=0, confirmed=0, spec=0, model_limitations=0, errors=0\ntriage: refuted=0, verified=4, unverifiable=0\nnext_steps:\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: onTokenReceived.requires, onTokenReceived.ensures, mint.requires, mint.ensures, setReceiveHook.requires, setReceiveHook.ensures, transfer.requires, transfer.ensures, approve.requires, transferFrom.requires, transferFrom.ensures, move.requires, move.ensures, notifyReceiver.requires, notifyReceiver.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: balanceOf.requires, balanceOf.ensures, transfer.requires, transfer.ensures, transferFrom.requires, transferFrom.ensures, lastTimeRewardApplicable.requires, lastTimeRewardApplicable.ensures, rewardPerToken.requires, rewardPerToken.ensures, earned.requires, earned.ensures, stake.requires, stake.ensures, withdraw.requires, withdraw.ensures, emergencyWithdraw.requires, emergencyWithdraw.ensures, getReward.requires, getReward.ensures, setPayoutAddress.requires, setPayoutAddress.ensures, claimFor.requires, claimFor.ensures, claimBonus.requires, claimBonus.ensures, notifyRewardAmount.requires, notifyRewardAmount.ensures, setOperator.requires, setOperator.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: onTokenReceived.requires, onTokenReceived.ensures, mint.requires, mint.ensures, setReceiveHook.requires, setReceiveHook.ensures, transfer.requires, transfer.ensures, approve.requires, transferFrom.requires, transferFrom.ensures, move.requires, move.ensures, notifyReceiver.requires, notifyReceiver.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: balanceOf.requires, balanceOf.ensures, transfer.requires, transfer.ensures, transferFrom.requires, transferFrom.ensures, lastTimeRewardApplicable.requires, lastTimeRewardApplicable.ensures, rewardPerToken.requires, rewardPerToken.ensures, earned.requires, earned.ensures, stake.requires, stake.ensures, withdraw.requires, withdraw.ensures, emergencyWithdraw.requires, emergencyWithdraw.ensures, getReward.requires, getReward.ensures, setPayoutAddress.requires, setPayoutAddress.ensures, claimFor.requires, claimFor.ensures, claimBonus.requires, claimBonus.ensures, notifyRewardAmount.requires, notifyRewardAmount.ensures, setOperator.requires, setOperator.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- レビュー専用のギャップはありません。

### 検出事項
- 検出事項はありません。
