atom helper(x: i64) -> i64 requires: x >= 0 && x <= 100; ensures: result >= 1; body: { x + 1 };
atom cc(x: i64) -> i64 requires: x >= 0 && x <= 100; ensures: true; body: { if x > 5 { helper(x) } else { 0 } };
atom absd(x: i64, y: i64) -> i64 requires: x >= 0 && x <= 1000 && y >= 0 && y <= 1000; ensures: result >= 0; body: { if x > y { x - y } else { y - x } };
atom band(x: i64, y: i64) -> i64 requires: x >= 0 && x <= 100 && y >= 0 && y <= 100; ensures: true; body: { if x > 5 && y > 5 { x + y } else { 0 } };
atom main() -> i64 requires: true; ensures: true; body: { cc(1) + absd(7, 3) + 3 };
