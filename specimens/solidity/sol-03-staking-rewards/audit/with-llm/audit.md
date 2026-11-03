## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/solidity/sol-03-staking-rewards`
- verification_status: `refuted`
- Summary: Audit directory: specimens/solidity/sol-03-staking-rewards\n  src/StakeToken.sol: 4 violations, 5 gaps\n  src/StakingRewards.sol: 11 violations, 9 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 4 files, 3 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: onTokenReceived.requires, onTokenReceived.ensures, vague_adjective at Position 2156-2166, conditional at Position 204-239, conditional at Position 3148-3187\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: transfer.requires, transfer.ensures, transferFrom.requires, transferFrom.ensures, earned.ensures, vague_adjective at Position 715-725, conditional at Position 1036-1053, conditional at Position 5546-5573\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 74-139\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, load.requires, expectRevert.requires, expectRevert.ensures, conditional at Position 436-529\n    command: mumei-agent validate-spec --input <spec> --format human

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
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: onTokenReceived.requires, onTokenReceived.ensures, vague_adjective at Position 2156-2166, conditional at Position 204-239, conditional at Position 3148-3187
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: transfer.requires, transfer.ensures, transferFrom.requires, transferFrom.ensures, earned.ensures, vague_adjective at Position 715-725, conditional at Position 1036-1053, conditional at Position 5546-5573
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
- `cross_validation_gaps`: ["src/StakeToken.sol: spec stronger than implementation: transferFrom", "src/StakeToken.sol: spec ambiguity (missing_requirement): move.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering move; none was stated.", "src/StakeToken.sol: spec ambiguity (missing_requirement): move.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering move; none was stated."]
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
- `cross_validation_gaps`
  - src/StakeToken.sol: spec stronger than implementation: transferFrom
  - src/StakeToken.sol: spec ambiguity (missing_requirement): move.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering move; none was stated.
  - src/StakeToken.sol: spec ambiguity (missing_requirement): move.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering move; none was stated.
  - src/StakeToken.sol: spec ambiguity (missing_requirement): notifyReceiver.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering notifyReceiver; none was stated.
  - src/StakeToken.sol: spec ambiguity (missing_requirement): notifyReceiver.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering notifyReceiver; none was stated.
  - src/StakingRewards.sol: spec stronger than implementation: rewardPerToken
  - src/StakingRewards.sol: spec ambiguity (missing_requirement): balanceOf.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering balanceOf; none was stated.
  - src/StakingRewards.sol: spec ambiguity (missing_requirement): balanceOf.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering balanceOf; none was stated.
  - src/StakingRewards.sol: spec ambiguity (missing_requirement): lastTimeRewardApplicable.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering lastTimeRewardApplicable; none was stated.
  - src/StakingRewards.sol: spec ambiguity (missing_requirement): lastTimeRewardApplicable.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering lastTimeRewardApplicable; none was stated.
- `spec_health_issues`
  - test/TestBase.sol: encoding-gap: panicCode: spec_lowering_failed: failed to lower ensures clause '((len(data) < 36 || data[0] != 78 || data[1] != 72 || data[2] != 123 || data[3] != 113) && result == u256 :: MAX) ||(len(data) >= 36 && data[0] == 78 && data[1] == 72 && data[2] == 123 && data[3] == 113 && result == decode_u256_be(data, 4, 32))': Type Error: len() expects an array or string argument; `data` is neither (constraints: ["((len(data) < 36 || data[0] != 78 || data[1] != 72 || data[2] != 123 || data[3] != 113) && result == u256 :: MAX) ||(len(data) >= 36 && data[0] == 78 && data[1] == 72 && data[2] == 123 && data[3] == 113 && result == decode_u256_be(data, 4, 32))"])
