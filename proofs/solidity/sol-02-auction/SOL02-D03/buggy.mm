struct Finalize {
    ok: bool,
    finalized: bool,
}

atom finalize(finalized: bool) -> Finalize
    requires: true;
    ensures: finalized == true => result.ok == false;
    body: {
        Finalize { ok: true, finalized: finalized }
    }
