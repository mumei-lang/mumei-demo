type Counter = Missing where v > 0;
atom f(x: Counter) -> i64 requires: true; ensures: result == x; body: { x };
atom main() -> i64 requires: true; ensures: result == 1; body: { f(1) };
