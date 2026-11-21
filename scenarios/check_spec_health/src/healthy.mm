atom healthy_spec(x: i64)
  requires: x >= 0;
  ensures: result == x;
  body: { x };
