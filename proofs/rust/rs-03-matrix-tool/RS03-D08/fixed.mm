struct Dims {
    rows: i64,
    cols: i64,
}

atom transpose(rows: i64, cols: i64) -> Dims
    requires: rows >= 1 && cols >= 1;
    ensures: result.rows == cols && result.cols == rows;
    body: {
        Dims { rows: cols, cols: rows }
    }
