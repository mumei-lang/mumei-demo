atom reorderPoint(total: i64, locations: i64) -> i64
    requires: total >= 0 && locations >= 0;
    ensures: (locations == 0 => result == 0) && (locations > 0 => result == total / locations);
    body: {
        if locations == 0 { 0 } else { total / locations }
    }
