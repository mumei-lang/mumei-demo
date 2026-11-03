atom itemHandler(parts: [i64], n: i64, sku: i64, has_sku: bool) -> i64
    requires: len(parts) == n && n >= 3;
    ensures: has_sku == false => result == 0;
    body: {
        parts[3]
    }
