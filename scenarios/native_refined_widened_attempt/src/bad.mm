type Big = u64 where v > 0;
atom f(x: Big) -> i64 requires: true; ensures: result == 1; body: { 1 };
atom main() -> i64 requires: true; ensures: result == 1; body: { f(3) };
