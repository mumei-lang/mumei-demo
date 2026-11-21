atom loop_count(n: i64) -> i64
requires: n >= 0 && n <= 10;
ensures: true;
body: {
    let i = 0;
    while i < n
    invariant: i >= 0 && i <= n
    decreases: n - i
    {
        i = i + 1;
    };
    i
};
atom main() -> i64
requires: true;
ensures: true;
body: { loop_count(3) };
