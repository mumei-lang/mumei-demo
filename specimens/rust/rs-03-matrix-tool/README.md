# rs-03-matrix-tool

A CLI that reads a whitespace-separated integer matrix from a text file and
runs one operation over it.

## Build

```bash
cargo build --release
```

## Usage

```bash
target/release/matrix-tool --input m.txt --op OP [--factor N] [--label S] [--out PATH]
```

Input format: one row per line, cells separated by whitespace:

```text
1 2 3
4 5 6
```

Ops:

- `invert` — invert a 2x2 matrix, prints the four f64 cells
- `mean` — integer mean of all cells
- `scale` — multiply every cell by `--factor`
- `transpose` — print the transposed matrix
- `report` — print per-column totals and append a labelled line to a summary file (`--out`, `--label`)
- `checksum` — additive byte checksum of the input file

The last op's result is also dropped into a small cache file for the next
invocation.
