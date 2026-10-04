# Logscan

A command-line report tool for access logs with timestamp, method, path,
status, and latency fields.

## Build and run

```bash
go build -o bin/logscan .
./bin/logscan -input testdata/access.log -top 5 -since 2026-01-01 \
  -out summary.txt -workers 4
```

Input paths are comma-separated. The report includes path counts, average
latency, and selected latency percentiles; the output is also compressed.
Optional flags select a time boundary, output name, worker count, and
percentile list.

## Scripts

`./run.sh` builds the program and processes the included sample. `./repro.sh`
builds the program and runs a set of command-line examples, including generated
inputs in its local working directory.
