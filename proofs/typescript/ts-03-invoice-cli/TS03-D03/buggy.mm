atom effectiveTaxRate(tax: i64, net: i64) -> i64
    requires: tax >= 0 && net >= 0;
    ensures: net == 0 => result == 0;
    body: {
        tax * 100 / net
    }
