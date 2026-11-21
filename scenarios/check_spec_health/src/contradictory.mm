atom contradictory_requires(x: i64)
  requires: x > 0 && x < 0;
  ensures: result == x;
  body: { x };
