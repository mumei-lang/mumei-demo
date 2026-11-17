struct Point { x: i64, on: bool }
atom read_x(p: Point) -> i64 requires: true; ensures: result == p.x; body: { p.x };
atom read_on(p: Point) -> bool requires: true; ensures: result == p.on; body: { p.on };
atom forward(p: Point) -> i64 requires: true; ensures: result == read_x(p); body: { read_x(p) };
atom main() -> i64 requires: true; ensures: result == 0; body: { 0 };
