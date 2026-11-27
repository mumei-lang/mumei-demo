// Reference migration target for the CI evidence-pack scenario.
// This contract is intentionally small: it demonstrates the CI verification
// gate shape without claiming equivalence to the Python fixture body.
atom divide(total: i64, count: i64)
    requires: count != 0;
    ensures: true;
    body: {
        total / count
    };
