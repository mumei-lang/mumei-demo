atom next_dose(dose: i64) -> i64
    requires: dose >= 0;
    ensures: result == dose + 1;
    body: {
        dose + 1
    };
