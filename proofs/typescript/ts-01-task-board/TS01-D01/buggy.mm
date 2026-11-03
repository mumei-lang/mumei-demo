atom canMove(from: i64, to: i64) -> bool
    requires: from >= 0 && from <= 4 && to >= 0 && to <= 4;
    ensures: result == ((from == 0 && to == 1) || (from == 1 && (to == 2 || to == 0)) || (from == 2 && (to == 3 || to == 1)) || (from == 3 && to == 4));
    body: {
        if from == 4 { false } else { (to - from == 1) || (to - from == 0 - 1) }
    }
