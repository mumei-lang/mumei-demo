struct Transfer {
    ok: bool,
    src: i64,
    dst: i64,
    house: i64,
}

atom transfer(src: i64, dst: i64, house: i64, dst_exists: bool, distinct_open: bool, amount: i64) -> Transfer
    requires: src >= 0;
    ensures: result.ok => amount > 0;
    body: {
        if !(src >= amount) { Transfer { ok: false, src: src, dst: dst, house: house } }
        else { if !dst_exists { Transfer { ok: false, src: src - amount - 25, dst: dst, house: house + 25 } }
        else { Transfer { ok: true, src: src - amount - 25, dst: dst + amount, house: house + 25 } } }
    }
