struct Stock {
    ok: bool,
    stock: i64,
    reserved: i64,
}

atom restockHandler(stock: i64, reserved: i64, packs: i64, per_pack: i64) -> Stock
    requires: stock >= 0 && stock <= 2147483647 && packs >= (0 - 2147483648) && packs <= 2147483647 && per_pack >= (0 - 2147483648) && per_pack <= 2147483647;
    ensures: result.ok => (result.stock >= stock && result.stock <= 2147483647);
    body: {
        Stock { ok: true, stock: stock + packs * per_pack, reserved: reserved }
    }
