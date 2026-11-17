type Flag = bool where v == true;
type NonNeg = i64 where v >= 0;
type Port = NonNeg where v <= 65535;
atom check(f: Flag) -> Port requires: true; ensures: result == 80; body: { 80 };
atom main() -> i64 requires: true; ensures: result == 80; body: { check(true) };
