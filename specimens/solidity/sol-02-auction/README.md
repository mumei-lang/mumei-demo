# sol-02-auction

A single-contract English (ascending-price) auction: outbid bidders are
refunded immediately, cancelled bids move to a pull-based `pendingReturns`
balance, the seller is paid at finalisation, and an early-bird bonus raffle
pays a funded pool to one early bidder.

## Contract

`src/EnglishAuction.sol`

- `init(seller, reservePrice, duration, minIncrementBps)` — one-time setup
  (end time plus a 15-minute late-bid grace window and an `endBlock`
  fallback).
- `bid()` payable — must meet `minNextBid()`; refunds the previous top
  bidder immediately.
- `cancelBid()` — moves the caller's recorded bid into `pendingReturns`.
- `withdraw()` — pulls the caller's `pendingReturns` balance.
- `hasEnded()` / `finalize()` — pays `highestBid` to the seller once both
  clocks have passed.
- `fundBonus()` payable / `drawEarlyBirdBonus()` — raffle among recorded
  early bidders (`earlyBirdCount`, `earlyBidders`).

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
