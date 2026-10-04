# Solidity specimens

Each specimen is a self-contained Foundry project (`forge build`,
`forge test`) with its happy path working and planted defects recorded in
`DEFECTS.json`. Tests use a local minimal `Vm` cheatcode interface — no
`forge-std`.

Each `foundry.toml` pins `solc_version = "0.8.24"` with `offline = true`, so
solc 0.8.24 must already be installed for forge (for example
`svm install 0.8.24`, or the official static binary placed at
`~/.local/share/svm/0.8.24/solc-0.8.24`).

| id | kind | description | default port | defects |
|----|------|-------------|--------------|---------|
| sol-01-token-vault | contract | ERC20-style token plus an ETH vault with pro-rata shares, withdraw fees and reward distribution | — | 10 |
| sol-02-auction | contract | English auction with instant refunds, pull-based cancellations, finalisation and an early-bird draw | — | 11 |
| sol-03-staking-rewards | contract | Reward-per-token staking pool with lockup, emergency exit, payout addresses and signed vouchers | — | 10 |
