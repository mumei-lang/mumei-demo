struct Transfer {
    ok: bool,
    src: i64,
    dst: i64,
    house: i64,
}

atom transfer(src: i64, dst: i64, house: i64, dst_exists: bool, distinct_open: bool, amount: i64) -> Transfer
    requires: src >= 0;
    ensures: result.ok == false => (result.src == src && result.dst == dst && result.house == house);
    body: {
        if amount <= 0 { Transfer { ok: false, src: src, dst: dst, house: house } }
        else { if !dst_exists || !distinct_open { Transfer { ok: false, src: src, dst: dst, house: house } }
        else { if !(src >= amount + 25) { Transfer { ok: false, src: src, dst: dst, house: house } }
        else { Transfer { ok: true, src: src - amount - 25, dst: dst + amount, house: house + 25 } } } }
    }
