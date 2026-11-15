extern "C" {
    fn getchar() -> i32;
}

atom main() -> i64
    requires: true;
    ensures: result >= 0;
    body: { 7 };
