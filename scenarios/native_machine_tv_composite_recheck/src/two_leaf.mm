struct P { x: i64, y: i64 }
atom sum(p: P) -> i64 requires: true; ensures: true; body: { p.x + p.y };
atom mk(a: i64, b: i64) -> P requires: true; ensures: true; body: { P { x: a, y: b } };
atom caller() -> i64 requires: true; ensures: true; body: { sum(mk(1, 2)) };
atom fwd(p: P) -> i64 requires: true; ensures: true; body: { sum(p) };
atom main() -> i64 requires: true; ensures: true; body: { 0 };
