atom pick(n: i64, i: i64) -> i64
    requires: 0 <= i && i < n;
    ensures: result == i;
    body: { i }

atom at(rows: i64, cols: i64, row: i64, col: i64) -> i64
    requires: rows >= 1 && cols >= 1 && row >= 0 && row < rows && col >= 0 && col < cols;
    ensures: result == row * cols + col;
    body: {
        pick(rows * cols, row * cols + col)
    }
