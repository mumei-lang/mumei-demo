// P9-F Self-Correction Protocol demo: intentionally buggy absolute value.

atom abs_nonnegative(x: i64)
    requires: true;
    ensures: result >= 0;
    body: {
        0 - x
    };
