atom overtime_minutes(daily: [i64], n: i64, threshold: i64) -> i64
    requires: len(daily) == n && n >= 1;
    ensures: result >= 0 && (daily[0] > threshold => result >= daily[0] - threshold);
    body: {
        let extra = 0;
        let i = 1;
        while i < n
        invariant: i >= 1 && i <= n && extra >= 0
        decreases: n - i
        {
            extra = extra + (if daily[i] > threshold { daily[i] - threshold } else { 0 });
            i = i + 1;
        };
        extra
    }
