atom fadd(x: f64, y: f64) -> f64 requires: true; ensures: true; body: { x * y + x };
atom feq(x: f64, y: f64) -> bool requires: true; ensures: result == (x == y); body: { x == y };
atom mixed(x: i64, y: f64) -> f64 requires: true; ensures: true; body: { y };
atom main() -> i64 requires: true; ensures: true; body: { 0 };
