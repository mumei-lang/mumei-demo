atom pick(n: i64, i: i64) -> i64
    requires: 0 <= i && i < n;
    ensures: result == i;
    body: { i }

atom percentileAt(n: i64, pct: i64) -> i64
    requires: n >= 0 && pct >= 0 && pct <= 100;
    ensures: n == 0 => result == 0;
    body: {
        if n == 0 { 0 } else { pick(n, if (n * pct + 99) / 100 - 1 < 0 { 0 } else { if (n * pct + 99) / 100 - 1 > n - 1 { n - 1 } else { (n * pct + 99) / 100 - 1 } }) }
    }
