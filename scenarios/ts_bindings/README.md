# TypeScript Lexical Binding Report (ts-bindings)

This optional scenario runs the in-process `ts-bindings` route on a tiny
TypeScript fixture. No external compiler or toolchain is required. The route's
versioned `profile` identifies the report; its JSON does not expose a separate
`schema_version` field.

| Step | What it does | What it does not do |
|---|---|---|
| 1 | Writes the report JSON and checks its profile, the `answer` reference-to-declaration link, and unresolved `missingName`. | Does not type-check, compile, prove, issue a verdict, provide trusted-safe evidence, produce an audit result, or award a Seal Grade. |

The report is conservative lexical binding metadata only.
