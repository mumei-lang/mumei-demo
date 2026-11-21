struct Q { a: i64, b: f64, c: i64, d: f64 }
atom sum4(q: Q) -> f64 requires: true; ensures: true; body: { q.b + q.d };
atom mk4(a: i64, b: f64, c: i64, d: f64) -> Q requires: true; ensures: true; body: { Q { a: a, b: b, c: c, d: d } };
atom caller(x: f64) -> f64 requires: true; ensures: true; body: { sum4(mk4(1, x, 2, x)) };
atom fwd(q: Q) -> f64 requires: true; ensures: true; body: { sum4(q) };
atom main() -> i64 requires: true; ensures: true; body: { 0 };
