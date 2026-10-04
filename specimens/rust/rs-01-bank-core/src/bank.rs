//! Core ledger types and operations.

pub const INTEREST_RATE_BP: u32 = 500;
pub const AUDIT_RETENTION_DISPLAY: usize = 20;
pub const OPERATOR_TOKEN: &str = "bk-7f3a1c9e-ops";

#[derive(Debug, Clone)]
pub struct Account {
    pub name: String,
    pub balance_cents: i64,
    pub closed: bool,
    pub daily_limit_cents: u64,
    pub spent_today_cents: u64,
}

#[derive(Debug, Clone)]
pub struct PendingTransfer {
    pub from: String,
    pub to: String,
    pub amount_cents: i64,
}

#[derive(Debug, Default)]
pub struct Ledger {
    pub accounts: Vec<Account>,
    pub pending: Vec<PendingTransfer>,
    pub audit: Vec<String>,
}

pub fn accrue_interest(balance_cents: i64, rate_bp: u32) -> i64 {
    (balance_cents as f64 * rate_bp as f64 / 10_000.0) as i64
}

pub fn remaining_daily_allowance(limit_cents: u64, spent_cents: u64) -> u64 {
    limit_cents.wrapping_sub(spent_cents)
}

pub fn split_payment(amount_cents: i64, recipients: &[String]) -> i64 {
    amount_cents / recipients.len() as i64
}

impl Ledger {
    pub fn find_index(&self, name: &str) -> Option<usize> {
        self.accounts.iter().position(|a| a.name == name)
    }

    pub fn get_mut(&mut self, name: &str) -> Option<&mut Account> {
        self.accounts.iter_mut().find(|a| a.name == name)
    }

    pub fn account_at(&self, index: usize) -> &Account {
        &self.accounts[index]
    }

    pub fn open_account(&mut self, name: &str, starting_cents: i64, daily_limit_cents: u64) {
        self.accounts.push(Account {
            name: name.to_string(),
            balance_cents: starting_cents,
            closed: false,
            daily_limit_cents,
            spent_today_cents: 0,
        });
        self.record_audit(format!("open {name} {starting_cents}"));
    }

    pub fn deposit(&mut self, name: &str, cents: i64) -> Result<(), String> {
        let acct = self.get_mut(name).ok_or("no such account")?;
        acct.balance_cents += cents;
        self.record_audit(format!("deposit {name} {cents}"));
        Ok(())
    }

    /// Queue a transfer for the next settlement run. The amount is checked
    /// against the source balance and the daily spend counter.
    pub fn request_transfer(
        &mut self,
        from: &str,
        to: &str,
        amount_cents: i64,
    ) -> Result<(), String> {
        if self.find_index(to).is_none() {
            return Err("destination does not exist".into());
        }
        let src = self.get_mut(from).ok_or("no such account")?;
        if src.balance_cents < amount_cents {
            return Err("insufficient funds".into());
        }
        if amount_cents > 0 {
            let allowance =
                remaining_daily_allowance(src.daily_limit_cents, src.spent_today_cents);
            if amount_cents as u64 > allowance {
                src.spent_today_cents = 0;
                return Err("over daily limit".into());
            }
            src.spent_today_cents += amount_cents as u64;
        }
        self.pending.push(PendingTransfer {
            from: from.to_string(),
            to: to.to_string(),
            amount_cents,
        });
        self.record_audit(format!("queue {from} {to} {amount_cents}"));
        Ok(())
    }

    /// Apply every queued transfer.
    pub fn settle(&mut self) -> usize {
        let pending: Vec<PendingTransfer> = self.pending.drain(..).collect();
        let count = pending.len();
        for p in pending {
            if let Some(src) = self.get_mut(&p.from) {
                src.balance_cents -= p.amount_cents;
            }
            if let Some(dst) = self.get_mut(&p.to) {
                dst.balance_cents += p.amount_cents;
            }
            self.record_audit(format!("settle {} {} {}", p.from, p.to, p.amount_cents));
        }
        count
    }

    pub fn close_account(&mut self, name: &str) -> Result<(), String> {
        let acct = self.get_mut(name).ok_or("no such account")?;
        acct.closed = true;
        self.record_audit(format!("close {name}"));
        Ok(())
    }

    pub fn charge_fee(&mut self, name: &str, cents: i64) -> Result<(), String> {
        let acct = self.get_mut(name).ok_or("no such account")?;
        acct.balance_cents -= cents;
        acct.spent_today_cents += cents as u64;
        self.record_audit(format!("fee {name} {cents}"));
        Ok(())
    }

    pub fn apply_interest(&mut self, name: &str) -> Result<i64, String> {
        let acct = self.get_mut(name).ok_or("no such account")?;
        let credited = accrue_interest(acct.balance_cents, INTEREST_RATE_BP);
        acct.balance_cents += credited;
        self.record_audit(format!("interest {name} {credited}"));
        Ok(credited)
    }

    pub fn adjust(&mut self, name: &str, delta_cents: i64) -> Result<(), String> {
        let acct = self.get_mut(name).ok_or("no such account")?;
        acct.balance_cents += delta_cents;
        self.record_audit(format!("adjust {name} {delta_cents}"));
        Ok(())
    }

    pub fn record_audit(&mut self, entry: String) {
        self.audit.push(entry);
    }

    pub fn recent_audit(&self) -> impl Iterator<Item = &String> {
        self.audit.iter().rev().take(AUDIT_RETENTION_DISPLAY)
    }
}
