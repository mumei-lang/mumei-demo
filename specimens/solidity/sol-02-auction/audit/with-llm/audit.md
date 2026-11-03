## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/solidity/sol-02-auction`
- verification_status: `refuted`
- Summary: Audit directory: specimens/solidity/sol-02-auction\n  src/EnglishAuction.sol: 11 violations, 3 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 3 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: bid.requires, bid.ensures, conditional at Position 2008-2140, conditional at Position 4931-4967\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 74-139\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, load.requires, expectRevert.requires, expectRevert.ensures, conditional at Position 436-529\n    command: mumei-agent validate-spec --input <spec> --format human

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
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: bid.requires, bid.ensures, conditional at Position 2008-2140, conditional at Position 4931-4967
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
6. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 74-139
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
7. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, load.requires, expectRevert.requires, expectRevert.ensures, conditional at Position 436-529
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["src/EnglishAuction.sol: spec stronger than implementation: minNextBid", "src/EnglishAuction.sol: spec ambiguity (missing_requirement): earlyBirdCount.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering earlyBirdCount; none was stated.", "src/EnglishAuction.sol: spec ambiguity (missing_requirement): earlyBirdCount.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering earlyBirdCount; none was stated."]
- `verification_violations`: ["src/EnglishAuction.sol: Solidity function `init` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless", "src/EnglishAuction.sol: Solidity function `bid` may be vulnerable to reentrancy: verified guard-state-machine trace shows an external call reachable in the Unlocked state before a later state write (Checks-Effects-Interactions violation; move state updates before external calls or add a reentrancy guard)", "src/EnglishAuction.sol: Solidity function `bid` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless"]

### 検出事項
- `verification_violations`
  - src/EnglishAuction.sol: Solidity function `init` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/EnglishAuction.sol: Solidity function `bid` may be vulnerable to reentrancy: verified guard-state-machine trace shows an external call reachable in the Unlocked state before a later state write (Checks-Effects-Interactions violation; move state updates before external calls or add a reentrancy guard)
  - src/EnglishAuction.sol: Solidity function `bid` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/EnglishAuction.sol: Solidity function `cancelBid` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/EnglishAuction.sol: Solidity function `withdraw` may be vulnerable to reentrancy: verified guard-state-machine trace shows an external call reachable in the Unlocked state before a later state write (Checks-Effects-Interactions violation; move state updates before external calls or add a reentrancy guard)
  - src/EnglishAuction.sol: Solidity function `withdraw` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/EnglishAuction.sol: Solidity function `finalize` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/EnglishAuction.sol: Solidity function `fundBonus` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
  - src/EnglishAuction.sol: Solidity function `drawEarlyBirdBonus` may be vulnerable to reentrancy: verified guard-state-machine trace shows an external call reachable in the Unlocked state before a later state write (Checks-Effects-Interactions violation; move state updates before external calls or add a reentrancy guard)
  - src/EnglishAuction.sol: Solidity function `drawEarlyBirdBonus` is an externally callable state-mutating function with no access-control guard (no `onlyOwner`-style modifier or `require(msg.sender == ...)`); confirm this is intentionally permissionless
- `cross_validation_gaps`
  - src/EnglishAuction.sol: spec stronger than implementation: minNextBid
  - src/EnglishAuction.sol: spec ambiguity (missing_requirement): earlyBirdCount.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering earlyBirdCount; none was stated.
  - src/EnglishAuction.sol: spec ambiguity (missing_requirement): earlyBirdCount.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering earlyBirdCount; none was stated.
- `spec_health_issues`
  - test/TestBase.sol: encoding-gap: panicCode: spec_lowering_failed: failed to lower ensures clause '((len(data) < 36 || data[0] != 78 || data[1] != 72 || data[2] != 123 || data[3] != 113) && result == u256 :: MAX) ||(len(data) >= 36 && data[0] == 78 && data[1] == 72 && data[2] == 123 && data[3] == 113 && result == decode_u256_be(data, 4, 32))': Type Error: len() expects an array or string argument; `data` is neither (constraints: ["((len(data) < 36 || data[0] != 78 || data[1] != 72 || data[2] != 123 || data[3] != 113) && result == u256 :: MAX) ||(len(data) >= 36 && data[0] == 78 && data[1] == 72 && data[2] == 123 && data[3] == 113 && result == decode_u256_be(data, 4, 32))"])
