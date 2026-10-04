## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/solidity/sol-01-token-vault`
- verification_status: `refuted`
- Summary: Audit directory: specimens/solidity/sol-01-token-vault\n  src/RewardVault.sol: 7 violations, 0 gaps\n  src/VaultToken.sol: 2 violations, 0 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 4 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: deposit.requires, deposit.ensures, previewDeposit.requires, previewDeposit.ensures, totalAssets.requires, totalAssets.ensures, sharePrice.ensures, sharesOf.ensures, withdraw.requires, withdraw.ensures, distributeRewards.requires, distributeRewards.ensures, claimRewards.requires, claimRewards.ensures, setFeeRecipient.requires, setFeeRecipient.ensures, setWithdrawFeeBps.requires, setWithdrawFeeBps.ensures, pause.requires, pause.ensures, unpause.requires, unpause.ensures, holderCount.requires, holderCount.ensures, sharesFor.requires, sharesFor.ensures, payout.requires, payout.ensures, payFee.requires, payFee.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: mint.requires, mint.ensures, transfer.requires, approve.requires, transferFrom.requires, move.requires, move.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: deposit.requires, deposit.ensures, previewDeposit.requires, previewDeposit.ensures, totalAssets.requires, totalAssets.ensures, sharePrice.ensures, sharesOf.ensures, withdraw.requires, withdraw.ensures, distributeRewards.requires, distributeRewards.ensures, claimRewards.requires, claimRewards.ensures, setFeeRecipient.requires, setFeeRecipient.ensures, setWithdrawFeeBps.requires, setWithdrawFeeBps.ensures, pause.requires, pause.ensures, unpause.requires, unpause.ensures, holderCount.requires, holderCount.ensures, sharesFor.requires, sharesFor.ensures, payout.requires, payout.ensures, payFee.requires, payFee.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: mint.requires, mint.ensures, transfer.requires, approve.requires, transferFrom.requires, move.requires, move.ensures
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
- `verification_violations`: ["src/RewardVault.sol: Solidity function `withdraw` can truncate `shares` in cast to `uint128` without a range contract (shares outside 0..=340282366920938463463374607431768211455 wraps)", "src/RewardVault.sol: Solidity function `deposit` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless", "src/RewardVault.sol: Solidity function `withdraw` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless"]

### 検出事項
- `verification_violations`
  - src/RewardVault.sol: Solidity function `withdraw` can truncate `shares` in cast to `uint128` without a range contract (shares outside 0..=340282366920938463463374607431768211455 wraps)
  - src/RewardVault.sol: Solidity function `deposit` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `withdraw` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `claimRewards` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `setFeeRecipient` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `setWithdrawFeeBps` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Z3 Counter-example: shares=340282366920938463463374607431768211456
  - src/VaultToken.sol: Solidity function `approve` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/VaultToken.sol: Solidity function `transferFrom` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
