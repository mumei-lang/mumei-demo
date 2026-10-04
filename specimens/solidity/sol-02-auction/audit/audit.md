## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/solidity/sol-02-auction`
- verification_status: `refuted`
- Summary: Audit directory: specimens/solidity/sol-02-auction\n  src/EnglishAuction.sol: 11 violations, 0 gaps\n  test/TestBase.sol: 0 violations, 0 gaps\n  test/Vm.sol: 0 violations, 0 gaps\nSummary: 3 files, 1 file with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: init.requires, init.ensures, minNextBid.requires, minNextBid.ensures, bid.requires, bid.ensures, cancelBid.requires, cancelBid.ensures, withdraw.requires, withdraw.ensures, hasEnded.requires, hasEnded.ensures, finalize.requires, finalize.ensures, earlyBirdCount.requires, earlyBirdCount.ensures, fundBonus.requires, fundBonus.ensures, drawEarlyBirdBonus.requires, drawEarlyBirdBonus.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: panicCode.requires, panicCode.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: deal.requires, deal.ensures, prank.requires, prank.ensures, startPrank.requires, startPrank.ensures, stopPrank.requires, stopPrank.ensures, warp.requires, warp.ensures, roll.requires, roll.ensures, load.requires, load.ensures, sign.requires, sign.ensures, addr.requires, addr.ensures, expectRevert.requires, expectRevert.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: init.requires, init.ensures, minNextBid.requires, minNextBid.ensures, bid.requires, bid.ensures, cancelBid.requires, cancelBid.ensures, withdraw.requires, withdraw.ensures, hasEnded.requires, hasEnded.ensures, finalize.requires, finalize.ensures, earlyBirdCount.requires, earlyBirdCount.ensures, fundBonus.requires, fundBonus.ensures, drawEarlyBirdBonus.requires, drawEarlyBirdBonus.ensures
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
