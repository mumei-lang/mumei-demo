# Security Policy

## Supported Versions

The project is pre-1.0. Security fixes are applied to the `main` branch and carried into the next release tag.

## Reporting a Vulnerability

Please do **not** open a public GitHub issue for security vulnerabilities.

Report vulnerabilities privately via [GitHub Security Advisories](https://github.com/mumei-lang/mumei-demo/security/advisories/new) ("Report a vulnerability"). If private vulnerability reporting is not yet enabled on this repository, contact the maintainer via their GitHub profile (https://github.com/AkiraTamai) instead of opening a public issue.

Please include:

- A description of the issue and its potential impact
- Steps to reproduce or a proof-of-concept
- Affected files, scenarios, or workflows

## Scope

In scope:

- The scenario/execution harness (`scripts/`, `Makefile` targets) and the dashboard under `dashboard/`
- CI/CD workflows under `.github/workflows/`
- Handling of secrets and credentials (`OPENAI_API_KEY`, tokens, certificates) in scripts, reports, and artifacts
- Injection or command-execution paths reachable from scenario definitions (`scenarios/*/scenario.json`), specimen inputs, or LLM-generated artifacts

Out of scope:

- Vulnerabilities in the sibling repositories [mumei](https://github.com/mumei-lang/mumei), [mumei-agent](https://github.com/mumei-lang/mumei-agent), and [mumei-lean](https://github.com/mumei-lang/mumei-lean) — report those in each repository
- Deliberately vulnerable code under `specimens/` (it is a planted-defect corpus used to exercise audit tooling)
- LLM output quality or correctness issues that are not exploitable
