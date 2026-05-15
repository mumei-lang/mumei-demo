// インスリンポンプ制御 - バグ入り実装
// 安全チェックをスキップし、過剰投与の可能性

effect InsulinPump
    states: [Idle, SafetyChecked, Delivered];
    initial: Idle;
    transition check: Idle -> SafetyChecked;
    transition deliver: SafetyChecked -> Delivered;

atom deliver_insulin(
    glucose: i64,
    requested_dose: i64,
    current_hour_dosage: i64,
    max_dose_per_hour: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Idle };
    effect_post: { InsulinPump: Delivered };
    requires: glucose >= 0 && requested_dose > 0 && max_dose_per_hour > 0;
    ensures: result == requested_dose;
    body: {
        perform InsulinPump.deliver;
        requested_dose
    };
