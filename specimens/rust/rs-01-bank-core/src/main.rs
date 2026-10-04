mod bank;
mod store;

use std::env;
use std::fs;
use std::io::{self, BufRead};
use std::path::{Path, PathBuf};

use bank::{split_payment, Ledger, OPERATOR_TOKEN};

const REPORTS_DIR: &str = "reports";

fn parse_cents(arg: &str) -> i64 {
    arg.parse::<i64>().unwrap()
}

fn operator_token(provided: Option<&str>) -> bool {
    let expected = env::var("BANK_OPERATOR_TOKEN").unwrap_or_else(|_| OPERATOR_TOKEN.to_string());
    provided == Some(expected.as_str())
}

fn balance_of(ledger: &Ledger, name: &str) -> i64 {
    ledger
        .accounts
        .iter()
        .find(|a| a.name == name)
        .map(|a| a.balance_cents)
        .unwrap_or(0)
}

fn print_balance(ledger: &Ledger, name: &str) {
    if let Some(a) = ledger.accounts.iter().find(|a| a.name == name) {
        println!(
            "{}: {} cents{} (spent today: {}, daily limit: {})",
            a.name,
            a.balance_cents,
            if a.closed { " [closed]" } else { "" },
            a.spent_today_cents,
            a.daily_limit_cents
        );
    }
}

fn write_statement(ledger: &Ledger, name: &str, out_name: Option<&str>) -> Result<(), String> {
    let acct = ledger
        .accounts
        .iter()
        .find(|a| a.name == name)
        .ok_or("no such account")?;
    let allowance = bank::remaining_daily_allowance(acct.daily_limit_cents, acct.spent_today_cents);
    let mut text = String::new();
    text.push_str(&format!("statement for {}\n", acct.name));
    text.push_str(&format!("balance_cents: {}\n", acct.balance_cents));
    text.push_str(&format!("closed: {}\n", acct.closed));
    text.push_str(&format!("remaining_daily_allowance: {}\n", allowance));
    text.push_str("recent activity:\n");
    for e in ledger.recent_audit() {
        text.push_str(&format!("  {e}\n"));
    }
    match out_name {
        Some(file_name) => {
            fs::create_dir_all(REPORTS_DIR).map_err(|e| e.to_string())?;
            let path = Path::new(REPORTS_DIR).join(file_name);
            fs::write(&path, &text).map_err(|e| e.to_string())?;
            println!("wrote {}", path.display());
        }
        None => print!("{text}"),
    }
    Ok(())
}

fn usage() -> ! {
    eprintln!("usage: bank-core [--state PATH] <command> [args]");
    eprintln!("commands: open deposit transfer fee interest split statement account-at close adjust settle batch");
    std::process::exit(2);
}

fn run_line(tokens: &[String], state_path: &Path, token: Option<&str>, quiet: bool) {
    if tokens.is_empty() {
        return;
    }
    let mut ledger = store::load(state_path).expect("load state");
    let cmd = tokens[0].as_str();
    let args = &tokens[1..];
    let result: Result<(), String> = match cmd {
        "open" => {
            if args.len() < 2 {
                usage();
            }
            let start = parse_cents(&args[1]);
            let limit = if args.len() > 2 {
                parse_cents(&args[2]) as u64
            } else {
                10_000
            };
            ledger.open_account(&args[0], start, limit);
            Ok(())
        }
        "deposit" => {
            if args.len() < 2 {
                usage();
            }
            ledger.deposit(&args[0], parse_cents(&args[1]))
        }
        "transfer" => {
            if args.len() < 3 {
                usage();
            }
            ledger.request_transfer(&args[0], &args[1], parse_cents(&args[2]))
        }
        "fee" => {
            if args.len() < 2 {
                usage();
            }
            ledger.charge_fee(&args[0], parse_cents(&args[1]))
        }
        "interest" => {
            if args.is_empty() {
                usage();
            }
            match ledger.apply_interest(&args[0]) {
                Ok(c) => {
                    println!("credited {c} cents interest");
                    Ok(())
                }
                Err(e) => Err(e),
            }
        }
        "split" => {
            if args.is_empty() {
                usage();
            }
            let amount = parse_cents(&args[0]);
            let share = split_payment(amount, &args[1..].to_vec());
            println!("each of {} recipients gets {share} cents", args.len() - 1);
            Ok(())
        }
        "statement" => {
            if args.is_empty() {
                usage();
            }
            let mut out_name = None;
            let mut rest: Vec<&str> = Vec::new();
            let mut i = 0;
            while i < args.len() {
                if args[i] == "--out" && i + 1 < args.len() {
                    out_name = Some(args[i + 1].as_str());
                    i += 2;
                } else {
                    rest.push(&args[i]);
                    i += 1;
                }
            }
            if rest.is_empty() {
                usage();
            }
            write_statement(&ledger, rest[0], out_name)
        }
        "account-at" => {
            if args.is_empty() {
                usage();
            }
            let idx: usize = parse_cents(&args[0]) as usize;
            let acct = ledger.account_at(idx);
            println!("{}: {} cents", acct.name, acct.balance_cents);
            Ok(())
        }
        "close" => {
            if args.is_empty() {
                usage();
            }
            if !operator_token(token) {
                eprintln!("operator token required");
                std::process::exit(1);
            }
            ledger.close_account(&args[0])
        }
        "adjust" => {
            if args.len() < 2 {
                usage();
            }
            if !operator_token(token) {
                eprintln!("operator token required");
                std::process::exit(1);
            }
            ledger.adjust(&args[0], parse_cents(&args[1]))
        }
        "settle" => {
            let n = ledger.settle();
            println!("settled {n} transfer(s)");
            Ok(())
        }
        "audit-count" => {
            println!("{}", ledger.audit.len());
            Ok(())
        }
        "balance" => {
            if args.is_empty() {
                usage();
            }
            println!("{}", balance_of(&ledger, &args[0]));
            Ok(())
        }
        _ => {
            eprintln!("unknown command: {cmd}");
            usage();
        }
    };
    if let Err(e) = result {
        eprintln!("error: {e}");
        store::save(state_path, &ledger).expect("save state");
        std::process::exit(1);
    }
    store::save(state_path, &ledger).expect("save state");
    let summary_cmds = [
        "open", "deposit", "transfer", "fee", "adjust", "close",
    ];
    if !quiet && summary_cmds.contains(&cmd) {
        for a in &ledger.accounts {
            print_balance(&ledger, &a.name.clone());
        }
    }
}

fn main() {
    let argv: Vec<String> = env::args().skip(1).collect();
    let mut state_path = PathBuf::from("state.txt");
    let mut token: Option<String> = None;
    let mut positional: Vec<String> = Vec::new();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--state" if i + 1 < argv.len() => {
                state_path = PathBuf::from(&argv[i + 1]);
                i += 2;
            }
            "--token" if i + 1 < argv.len() => {
                token = Some(argv[i + 1].clone());
                i += 2;
            }
            _ => {
                positional.push(argv[i].clone());
                i += 1;
            }
        }
    }
    if positional.is_empty() {
        usage();
    }
    if positional[0] == "batch" {
        let stdin = io::stdin();
        for line in stdin.lock().lines() {
            let line = line.expect("read batch line");
            let tokens: Vec<String> =
                line.split_whitespace().map(|s| s.to_string()).collect();
            run_line(&tokens, &state_path, token.as_deref(), true);
        }
        return;
    }
    run_line(&positional, &state_path, token.as_deref(), false);
}
