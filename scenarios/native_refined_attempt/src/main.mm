type Port = i64 where v >= 1 && v <= 65535;
atom listen(x: Port) -> Port requires: true; ensures: result == x; body: { x };
atom main() -> i64 requires: true; ensures: result == 80; body: { listen(80) };
