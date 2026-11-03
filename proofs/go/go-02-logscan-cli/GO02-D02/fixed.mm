atom formatSummary(count: i64, total: i64) -> i64
    requires: count >= 0 && total >= 0;
    ensures: (count == 0 => result == 0) && (count > 0 => result == total / count);
    body: {
        if count > 0 { total / count } else { 0 }
    }
