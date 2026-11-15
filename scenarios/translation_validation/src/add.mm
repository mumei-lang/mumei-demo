atom add(a: i64, b: i64) -> i64
    requires: a >= 0 && b >= 0;
    ensures: result == a + b;
    body: { a + b };

atom main() -> i64
    requires: true;
    ensures: result >= 0;
    body: { add(3, 7) };
