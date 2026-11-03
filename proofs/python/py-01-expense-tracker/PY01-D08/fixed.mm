atom subcategory(parts: [i64], n: i64, label: i64) -> i64
    requires: len(parts) == n && n >= 1 && parts[0] == label;
    ensures: n == 1 => result == label;
    body: {
        if n >= 2 { parts[1] } else { label }
    }
