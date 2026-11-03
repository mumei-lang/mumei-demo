atom paginate(n: i64, page: i64, size: i64) -> i64
    requires: n >= 0 && page >= 1 && size >= 1;
    ensures: page * size <= n => result == size;
    body: {
        let start = (page - 1) * size;
        let end = start + size - 1;
        (if end > n { n } else { end }) - (if start > n { n } else { start })
    }
