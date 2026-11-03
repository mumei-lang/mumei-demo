atom share_of_total(part: i64, whole: i64) -> i64
    requires: part >= 0 && whole >= 0;
    ensures: whole == 0 => result == 0;
    body: {
        part / whole
    }
