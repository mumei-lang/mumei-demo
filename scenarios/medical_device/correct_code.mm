// インスリンポンプ制御 - 正しい実装
// 境界チェックと安全状態遷移で投与量を制限

effect InsulinPump
    states: [Idle, SafetyChecked, Delivered];
    initial: Idle;
    transition check: Idle -> SafetyChecked;
    transition deliver: SafetyChecked -> Delivered;

atom check_dosage_bounds(
    glucose: i64,
    requested_dose: i64,
    current_hour_dosage: i64,
    max_dose_per_hour: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Idle };
    effect_post: { InsulinPump: SafetyChecked };
    requires: glucose >= 70 && requested_dose > 0 && current_hour_dosage >= 0 && max_dose_per_hour > 0;
    requires: current_hour_dosage + requested_dose <= max_dose_per_hour;
    ensures: result == requested_dose;
    ensures: result <= max_dose_per_hour - current_hour_dosage;
    body: {
        perform InsulinPump.check;
        requested_dose
    };

atom commit_insulin_delivery(
    dose: i64,
    current_hour_dosage: i64,
    max_dose_per_hour: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: SafetyChecked };
    effect_post: { InsulinPump: Delivered };
    requires: dose > 0 && current_hour_dosage >= 0 && max_dose_per_hour > 0;
    requires: current_hour_dosage + dose <= max_dose_per_hour;
    ensures: result == dose;
    ensures: result <= max_dose_per_hour - current_hour_dosage;
    body: {
        perform InsulinPump.deliver;
        dose
    };

atom deliver_insulin(
    glucose: i64,
    requested_dose: i64,
    current_hour_dosage: i64,
    max_dose_per_hour: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Idle };
    effect_post: { InsulinPump: Delivered };
    requires: glucose >= 70 && requested_dose > 0 && current_hour_dosage >= 0 && max_dose_per_hour > 0;
    requires: current_hour_dosage + requested_dose <= max_dose_per_hour;
    ensures: result == requested_dose;
    ensures: result <= max_dose_per_hour - current_hour_dosage;
    body: {
        check_dosage_bounds(glucose, requested_dose, current_hour_dosage, max_dose_per_hour);
        commit_insulin_delivery(requested_dose, current_hour_dosage, max_dose_per_hour)
    };
