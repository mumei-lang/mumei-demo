// P9-F Self-Correction Protocol demo: corrected absolute value.

atom abs_nonnegative(x: i64)
    requires: true;
    ensures: result >= 0;
    body: {
        if x >= 0 { x } else { 0 - x }
    };
