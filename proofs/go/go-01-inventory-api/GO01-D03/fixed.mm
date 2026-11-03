struct Stock {
    ok: bool,
    stock: i64,
    reserved: i64,
}

atom releaseHandler(stock: i64, reserved: i64, qty: i64) -> Stock
    requires: stock >= 0 && reserved >= 0;
    ensures: result.ok => result.reserved >= 0;
    body: {
        if qty <= 0 { Stock { ok: false, stock: stock, reserved: reserved } }
        else { if reserved < qty { Stock { ok: false, stock: stock, reserved: reserved } }
        else { Stock { ok: true, stock: stock + qty, reserved: reserved - qty } } }
    }
