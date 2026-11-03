struct Window {
    ok: bool,
    start: i64,
}

atom page(n: i64, offset: i64, limit: i64) -> Window
    requires: n >= 0;
    ensures: result.ok => (result.start >= 0 && result.start <= n && (offset <= n => result.start == offset));
    body: {
        if offset < 0 { Window { ok: true, start: (if n + offset < 0 { 0 } else { n + offset }) } }
        else { Window { ok: true, start: (if offset > n { n } else { offset }) } }
    }
