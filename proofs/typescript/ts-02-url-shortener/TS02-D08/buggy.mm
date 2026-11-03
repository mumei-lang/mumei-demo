atom normalizeAlias(n: i64) -> i64
    requires: n >= 1 && n <= 8;
    ensures: result == n;
    body: {
        if n > 7 { 7 } else { n }
    }
