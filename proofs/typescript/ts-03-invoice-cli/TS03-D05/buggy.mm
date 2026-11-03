atom pick(n: i64, i: i64) -> i64
    requires: 0 <= i && i < n;
    ensures: result == i;
    body: { i }

atom pageFooters(n: i64, per_page: i64, page: i64) -> i64
    requires: per_page >= 1 && n > per_page && page >= 0 && page * per_page < n;
    ensures: result >= page * per_page && result < n;
    body: {
        let first = pick(n, page * per_page);
        pick(n, page * per_page + per_page - 1)
    }
