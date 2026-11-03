## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/solidity/sol-01-token-vault`
- verification_status: `refuted`
- Summary: Audit directory: specimens/solidity/sol-01-token-vault\n  src/RewardVault.sol: 5 violations, 10 gaps\n  src/VaultToken.sol: 2 violations, 4 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 4 files, 3 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: rewards.ensures, unpause.requires, unpause.ensures, accrue.requires, accrue.ensures, payout.requires, payout.ensures, conditional at Position 2578-2615\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 995-1005\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 74-139\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, load.requires, expectRevert.requires, expectRevert.ensures, conditional at Position 436-529\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
3. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: rewards.ensures, unpause.requires, unpause.ensures, accrue.requires, accrue.ensures, payout.requires, payout.ensures, conditional at Position 2578-2615
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 995-1005
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
6. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
7. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 74-139
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
8. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, load.requires, expectRevert.requires, expectRevert.ensures, conditional at Position 436-529
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["src/RewardVault.sol: spec ambiguity (missing_requirement): totalAssets.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering totalAssets; none was stated.", "src/RewardVault.sol: spec ambiguity (missing_requirement): totalAssets.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering totalAssets; none was stated.", "src/RewardVault.sol: spec ambiguity (missing_requirement): sharesOf.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering sharesOf; none was stated."]
- `verification_violations`: ["src/RewardVault.sol: Solidity function `withdraw` can truncate `shares` in cast to `uint128` without a range contract (shares outside 0..=340282366920938463463374607431768211455 wraps)", "src/RewardVault.sol: Solidity function `deposit` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless", "src/RewardVault.sol: Solidity function `withdraw` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless"]

### 検出事項
- `verification_violations`
  - src/RewardVault.sol: Solidity function `withdraw` can truncate `shares` in cast to `uint128` without a range contract (shares outside 0..=340282366920938463463374607431768211455 wraps)
  - src/RewardVault.sol: Solidity function `deposit` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `withdraw` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Solidity function `claimRewards` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/RewardVault.sol: Z3 Counter-example: shares=340282366920938463463374607431768211456
  - src/VaultToken.sol: Solidity function `approve` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/VaultToken.sol: Solidity function `transferFrom` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
- `cross_validation_gaps`
  - src/RewardVault.sol: spec ambiguity (missing_requirement): totalAssets.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering totalAssets; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): totalAssets.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering totalAssets; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): sharesOf.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering sharesOf; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): setWithdrawFeeBps.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering setWithdrawFeeBps; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): setWithdrawFeeBps.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering setWithdrawFeeBps; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): sharesFor.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering sharesFor; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): sharesFor.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering sharesFor; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): pending.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering pending; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): payFee.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering payFee; none was stated.
  - src/RewardVault.sol: spec ambiguity (missing_requirement): payFee.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering payFee; none was stated.
- `spec_health_issues`
  - test/TestBase.sol: encoding-gap: panicCode: spec_lowering_failed: failed to lower ensures clause '((len(data) < 36 || data[0] != 78 || data[1] != 72 || data[2] != 123 || data[3] != 113) && result == u256 :: MAX) ||(len(data) >= 36 && data[0] == 78 && data[1] == 72 && data[2] == 123 && data[3] == 113 && result == decode_u256_be(data, 4, 32))': Type Error: len() expects an array or string argument; `data` is neither (constraints: ["((len(data) < 36 || data[0] != 78 || data[1] != 72 || data[2] != 123 || data[3] != 113) && result == u256 :: MAX) ||(len(data) >= 36 && data[0] == 78 && data[1] == 72 && data[2] == 123 && data[3] == 113 && result == decode_u256_be(data, 4, 32))"])
