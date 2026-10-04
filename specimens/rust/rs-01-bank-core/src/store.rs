//! Line-oriented persistence for the ledger.
//!
//! Each record is a single `|`-separated line:
//!   `A|name|balance_cents|closed|daily_limit_cents|spent_today_cents`
//!   `P|from|to|amount_cents`
//!   `L|entry` (audit log line)

use std::fs;
use std::io;
use std::path::Path;

use crate::bank::{Account, Ledger, PendingTransfer};

pub fn load(path: &Path) -> io::Result<Ledger> {
    let mut ledger = Ledger::default();
    let text = match fs::read_to_string(path) {
        Ok(t) => t,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(ledger),
        Err(e) => return Err(e),
    };
    for line in text.lines() {
        let parts: Vec<&str> = line.split('|').collect();
        match parts.as_slice() {
            ["A", name, balance, closed, limit, spent] => {
                ledger.accounts.push(Account {
                    name: name.to_string(),
                    balance_cents: balance.parse().unwrap_or(0),
                    closed: *closed == "1",
                    daily_limit_cents: limit.parse().unwrap_or(0),
                    spent_today_cents: spent.parse().unwrap_or(0),
                });
            }
            ["P", from, to, amount] => {
                ledger.pending.push(PendingTransfer {
                    from: from.to_string(),
                    to: to.to_string(),
                    amount_cents: amount.parse().unwrap_or(0),
                });
            }
            ["L", rest @ ..] => {
                ledger.audit.push(rest.join("|"));
            }
            _ => {}
        }
    }
    Ok(ledger)
}

pub fn save(path: &Path, ledger: &Ledger) -> io::Result<()> {
    let mut out = String::new();
    for a in &ledger.accounts {
        out.push_str(&format!(
            "A|{}|{}|{}|{}|{}\n",
            a.name,
            a.balance_cents,
            if a.closed { "1" } else { "0" },
            a.daily_limit_cents,
            a.spent_today_cents
        ));
    }
    for p in &ledger.pending {
        out.push_str(&format!("P|{}|{}|{}\n", p.from, p.to, p.amount_cents));
    }
    for e in &ledger.audit {
        out.push_str(&format!("L|{}\n", e));
    }
    fs::write(path, out)
}
