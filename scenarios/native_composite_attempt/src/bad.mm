type Port = i64 where v >= 1 && v <= 65535;
struct S { port: Port }
atom f(s: S) -> i64 requires: true; ensures: result >= 1; body: { s.port };
atom main() -> i64 requires: true; ensures: result == 1; body: { 1 };
