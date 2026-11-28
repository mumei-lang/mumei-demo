## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/solidity/sol-01-token-vault`
- verification_status: `verified`
- finding_counts: `code=3, confirmed=0, spec=1, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `1`
- Summary: Audit directory: specimens/solidity/sol-01-token-vault\n  src/RewardVault.sol: 3 violations, 1 gap\n  src/VaultToken.sol: 0 violations, 0 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 4 files, 1 file with issues, 1 file with spec diagnostics\nfinding_counts: code=3, confirmed=0, spec=1, model_limitations=0, errors=0\ntriage: refuted=0, verified=4, unverifiable=0\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: deposit.requires, deposit.ensures, previewDeposit.requires, previewDeposit.ensures, totalAssets.requires, totalAssets.ensures, sharePrice.ensures, sharesOf.requires, sharesOf.ensures, withdraw.requires, withdraw.ensures, distributeRewards.requires, distributeRewards.ensures, claimRewards.requires, claimRewards.ensures, setFeeRecipient.requires, setFeeRecipient.ensures, setWithdrawFeeBps.requires, setWithdrawFeeBps.ensures, pause.requires, pause.ensures, unpause.requires, unpause.ensures, holderCount.requires, holderCount.ensures, sharesFor.requires, sharesFor.ensures, payout.requires, payout.ensures, payFee.requires, payFee.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: mint.requires, mint.ensures, transfer.requires, approve.requires, transferFrom.requires, move.requires, move.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: deposit.requires, deposit.ensures, previewDeposit.requires, previewDeposit.ensures, totalAssets.requires, totalAssets.ensures, sharePrice.ensures, sharesOf.requires, sharesOf.ensures, withdraw.requires, withdraw.ensures, distributeRewards.requires, distributeRewards.ensures, claimRewards.requires, claimRewards.ensures, setFeeRecipient.requires, setFeeRecipient.ensures, setWithdrawFeeBps.requires, setWithdrawFeeBps.ensures, pause.requires, pause.ensures, unpause.requires, unpause.ensures, holderCount.requires, holderCount.ensures, sharesFor.requires, sharesFor.ensures, payout.requires, payout.ensures, payFee.requires, payFee.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: mint.requires, mint.ensures, transfer.requires, approve.requires, transferFrom.requires, move.requires, move.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
6. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["src/RewardVault.sol: spec precondition assumed, not enforced, by `sharePrice`"]
- `verification_violations`: ["src/RewardVault.sol: Solidity function `setFeeRecipient` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless", "src/RewardVault.sol: Solidity function `setWithdrawFeeBps` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless", "src/RewardVault.sol: Solidity function `_payFee` discards the success flag of a low-level value call at line 171"]

### 検出事項
- `verification_violations`
  - src/RewardVault.sol: Solidity function `setFeeRecipient` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `setWithdrawFeeBps` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `_payFee` discards the success flag of a low-level value call at line 171
- `cross_validation_gaps`
  - src/RewardVault.sol: spec precondition assumed, not enforced, by `sharePrice`
