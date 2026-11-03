struct Stock {
    ok: bool,
    stock: i64,
    reserved: i64,
}

atom releaseHandler(stock: i64, reserved: i64, qty: i64) -> Stock
    requires: stock >= 0 && reserved >= 0;
    ensures: result.ok => result.reserved >= 0;
    body: {
        Stock { ok: true, stock: stock + qty, reserved: reserved - qty }
    }
