// Human review demo: trusted atoms must be explicitly reviewed before
// downstream automation relies on their contracts.

trusted atom external_risk_score(user_id: i64)
    requires: user_id >= 0;
    ensures: result >= 0;
    body: {
        0
    };

atom approve_low_risk_transfer(user_id: i64, amount: i64)
    requires: user_id >= 0 && amount >= 0;
    ensures: result >= 0;
    body: {
        let score = external_risk_score(user_id);
        score + amount
    };
