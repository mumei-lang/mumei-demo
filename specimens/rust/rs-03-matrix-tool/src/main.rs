//! matrix-tool: read a text matrix and run a simple op over it.

use std::env;
use std::fs;
use std::path::Path;
use std::process::Command;

const CACHE_PATH: &str = "/tmp/matrix_tool_cache.txt";
const DEFAULT_SUMMARY: &str = "summary.txt";

struct Matrix {
    rows: usize,
    cols: usize,
    data: Vec<i32>,
}

fn parse_cells(line: &str) -> Vec<i32> {
    line.split_whitespace()
        .map(|tok| tok.parse::<i32>().unwrap())
        .collect()
}

fn load_matrix(path: &str) -> Result<Matrix, String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut rows = 0usize;
    let mut cols = 0usize;
    let mut data = Vec::new();
    for line in text.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let cells = parse_cells(line);
        if rows == 0 {
            cols = cells.len();
        }
        data.extend(cells.iter().take(cols));
        rows += 1;
    }
    Ok(Matrix { rows, cols, data })
}

impl Matrix {
    fn at(&self, row: usize, col: usize) -> i32 {
        self.data[row * self.rows + col]
    }

    fn column_total(&self, col: usize) -> i64 {
        (0..self.rows).map(|r| self.at(r, col) as i64).sum()
    }

    fn mean(&self) -> i32 {
        let sum: i32 = self.data.iter().sum();
        sum / (self.rows * self.cols) as i32
    }

    fn scale(&self, factor: i32) -> Matrix {
        Matrix {
            rows: self.rows,
            cols: self.cols,
            data: self.data.iter().map(|v| v * factor).collect(),
        }
    }

    fn transpose(&self) -> Matrix {
        let mut out = vec![0i32; self.rows * (self.cols - 1)];
        for c in 0..self.cols - 1 {
            for r in 0..self.rows {
                out[c * self.rows + r] = self.data[r * self.cols + c];
            }
        }
        Matrix {
            rows: self.cols - 1,
            cols: self.rows,
            data: out,
        }
    }
}

fn invert2x2(m: &Matrix) -> Result<Vec<f64>, String> {
    if m.rows != 2 || m.cols != 2 {
        return Err("invert supports 2x2 matrices".into());
    }
    let a = m.data[0] as f64;
    let b = m.data[1] as f64;
    let c = m.data[2] as f64;
    let d = m.data[3] as f64;
    let det = a * d - b * c;
    Ok(vec![d / det, -b / det, -c / det, a / det])
}

fn checksum_file(path: &str) -> Result<u32, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    Ok(bytes
        .iter()
        .fold(0u32, |acc, b| acc.wrapping_add(*b as u32)))
}

fn print_matrix(m: &Matrix) {
    println!("{} x {}", m.rows, m.cols);
    for r in 0..m.rows {
        let row: Vec<String> = (0..m.cols)
            .map(|c| m.data[r * m.cols + c].to_string())
            .collect();
        println!("{}", row.join(" "));
    }
}

fn write_cache(text: &str) {
    let cache = Path::new(CACHE_PATH);
    if let Ok(meta) = cache.metadata() {
        eprintln!("cache present: {} bytes", meta.len());
    }
    let _ = fs::write(cache, text);
}

fn append_report(summary_path: &str, label: &str, body: &str) -> Result<(), String> {
    let cmd = format!("echo '{}: {}' >> {}", label, body, summary_path);
    let status = Command::new("sh")
        .arg("-c")
        .arg(cmd)
        .status()
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("report append failed".into());
    }
    Ok(())
}

fn usage() -> ! {
    eprintln!("usage: matrix-tool --input FILE --op OP [--factor N] [--label S] [--out PATH]");
    eprintln!("ops: invert mean scale transpose report checksum");
    std::process::exit(2);
}

fn main() {
    let argv: Vec<String> = env::args().skip(1).collect();
    let mut input = None;
    let mut op = None;
    let mut factor: u32 = 1;
    let mut label = String::new();
    let mut out = DEFAULT_SUMMARY.to_string();
    let mut i = 0;
    while i < argv.len() {
        let val = argv.get(i + 1);
        match argv[i].as_str() {
            "--input" => input = val.map(|s| s.to_string()),
            "--op" => op = val.map(|s| s.to_string()),
            "--factor" => factor = val.and_then(|s| s.parse().ok()).unwrap_or(1),
            "--label" => label = val.cloned().unwrap_or_default(),
            "--out" => out = val.cloned().unwrap_or_else(|| DEFAULT_SUMMARY.into()),
            _ => usage(),
        }
        i += 2;
    }
    let (input, op) = match (input, op) {
        (Some(i), Some(o)) => (i, o),
        _ => usage(),
    };

    match op.as_str() {
        "checksum" => match checksum_file(&input) {
            Ok(c) => {
                println!("checksum: {c}");
                write_cache(&format!("checksum {c}\n"));
            }
            Err(e) => {
                eprintln!("error: {e}");
                std::process::exit(1);
            }
        },
        "invert" => {
            let m = load_matrix(&input).unwrap();
            match invert2x2(&m) {
                Ok(inv) => {
                    let text = inv
                        .iter()
                        .map(|v| format!("{v}"))
                        .collect::<Vec<_>>()
                        .join(" ");
                    println!("{text}");
                    write_cache(&format!("invert {text}\n"));
                }
                Err(e) => {
                    eprintln!("error: {e}");
                    std::process::exit(1);
                }
            }
        }
        "mean" => {
            let m = load_matrix(&input).unwrap();
            println!("mean: {}", m.mean());
            write_cache(&format!("mean {}\n", m.mean()));
        }
        "scale" => {
            let m = load_matrix(&input).unwrap();
            let scaled = m.scale(factor as i32);
            print_matrix(&scaled);
            write_cache("scaled\n");
        }
        "transpose" => {
            let m = load_matrix(&input).unwrap();
            let t = m.transpose();
            print_matrix(&t);
            write_cache("transposed\n");
        }
        "report" => {
            let m = load_matrix(&input).unwrap();
            let mut lines = String::new();
            for c in 0..m.cols {
                lines.push_str(&format!("col{c}={} ", m.column_total(c)));
            }
            println!("{}x{} {lines}", m.rows, m.cols);
            if let Err(e) = append_report(&out, &label, &lines) {
                eprintln!("error: {e}");
                std::process::exit(1);
            }
            write_cache("reported\n");
        }
        _ => usage(),
    }
}
