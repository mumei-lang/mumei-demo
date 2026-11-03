struct Finalize {
    ok: bool,
    finalized: bool,
}

atom finalize(finalized: bool) -> Finalize
    requires: true;
    ensures: finalized == true => result.ok == false;
    body: {
        if finalized { Finalize { ok: false, finalized: finalized } } else { Finalize { ok: true, finalized: true } }
    }
