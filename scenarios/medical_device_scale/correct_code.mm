// Medical Device Control at operational scale: multi-stage insulin therapy cycle.
// Priority 16 large-scale case: the therapy pipeline is a nine-state temporal
// effect machine composed from atom-local obligations only. Every composite
// stage derives its postcondition from the ensures of the atoms it calls.

type Units = i64 where v >= 0 && v <= 250;
type Percent = i64 where v >= 0 && v <= 100;

effect InsulinPump
    states: [
        Idle,
        SelfTested,
        SensorsValidated,
        ProfileLoaded,
        DoseComputed,
        LimitsChecked,
        InterlockArmed,
        Delivered
    ];
    initial: Idle;
    transition self_test: Idle -> SelfTested;
    transition validate: SelfTested -> SensorsValidated;
    transition load_profile: SensorsValidated -> ProfileLoaded;
    transition compute: ProfileLoaded -> DoseComputed;
    transition check_limits: DoseComputed -> LimitsChecked;
    transition arm: LimitsChecked -> InterlockArmed;
    transition deliver: InterlockArmed -> Delivered;
    transition journal: Delivered -> Delivered;
    transition reset: Delivered -> Idle;
    transition abort: LimitsChecked -> Idle;

// ---------------------------------------------------------------------------
// Layer 0: pure arithmetic leaves
// ---------------------------------------------------------------------------

atom floor_at_zero(value: i64)
    requires: value >= -1000 && value <= 1000;
    ensures: result >= 0;
    ensures: result <= 1000;
    ensures: result <= value || result == 0;
    body: {
        if value >= 0 { value } else { 0 }
    };

atom cap_at(value: i64, ceiling: i64)
    requires: value >= 0 && ceiling >= 0 && value <= 1000 && ceiling <= 1000;
    ensures: result >= 0;
    ensures: result <= ceiling;
    ensures: result <= value;
    body: {
        if value <= ceiling { value } else { ceiling }
    };

atom clamp_to_window(value: i64, ceiling: i64)
    requires: value >= -1000 && value <= 1000 && ceiling >= 0 && ceiling <= 1000;
    ensures: result >= 0;
    ensures: result <= ceiling;
    body: {
        cap_at(floor_at_zero(value), ceiling)
    };

atom smaller_of(left: i64, right: i64)
    requires: left >= 0 && right >= 0 && left <= 1000 && right <= 1000;
    ensures: result >= 0;
    ensures: result <= left;
    ensures: result <= right;
    body: {
        if left <= right { left } else { right }
    };

// ---------------------------------------------------------------------------
// Layer 1: pure clinical predicates
// ---------------------------------------------------------------------------

atom glucose_plausible(glucose: i64)
    requires: glucose >= 0 && glucose <= 600;
    ensures: result >= 0 && result <= 1;
    ensures: result == 1 || glucose < 70 || glucose > 400;
    body: {
        if glucose >= 70 { if glucose <= 400 { 1 } else { 0 } } else { 0 }
    };

atom trend_bounded(delta_per_minute: i64)
    requires: delta_per_minute >= -50 && delta_per_minute <= 50;
    ensures: result >= 0 && result <= 1;
    body: {
        if delta_per_minute >= -10 { if delta_per_minute <= 10 { 1 } else { 0 } } else { 0 }
    };

atom calibration_fresh(minutes_since_calibration: i64)
    requires: minutes_since_calibration >= 0 && minutes_since_calibration <= 10000;
    ensures: result >= 0 && result <= 1;
    body: {
        if minutes_since_calibration <= 720 { 1 } else { 0 }
    };

atom battery_sufficient(battery_percent: Percent)
    requires: battery_percent >= 0 && battery_percent <= 100;
    ensures: result >= 0 && result <= 1;
    body: {
        if battery_percent >= 15 { 1 } else { 0 }
    };

atom occlusion_clear(line_pressure: i64)
    requires: line_pressure >= 0 && line_pressure <= 1000;
    ensures: result >= 0 && result <= 1;
    body: {
        if line_pressure <= 300 { 1 } else { 0 }
    };

atom reservoir_sufficient(reservoir_units: Units, planned_units: Units)
    requires: reservoir_units >= 0 && reservoir_units <= 250;
    requires: planned_units >= 0 && planned_units <= 250;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || reservoir_units >= planned_units;
    body: {
        if reservoir_units >= planned_units { 1 } else { 0 }
    };

atom all_of_two(first: i64, second: i64)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 1 || first == 0 || second == 0;
    body: {
        if first == 1 { second } else { 0 }
    };

atom all_of_three(first: i64, second: i64, third: i64)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1 && third >= 0 && third <= 1;
    ensures: result >= 0 && result <= 1;
    body: {
        let head = all_of_two(first, second);
        all_of_two(head, third)
    };

// ---------------------------------------------------------------------------
// Layer 2: pure dose planning
// ---------------------------------------------------------------------------

atom correction_component(glucose: i64, target: i64)
    requires: glucose >= 70 && glucose <= 400 && target >= 80 && target <= 140;
    ensures: result >= 0;
    ensures: result <= 320;
    body: {
        floor_at_zero(glucose - target)
    };

atom carbohydrate_component(carbohydrate_grams: i64)
    requires: carbohydrate_grams >= 0 && carbohydrate_grams <= 200;
    ensures: result >= 0;
    ensures: result <= 200;
    body: {
        carbohydrate_grams
    };

atom raw_bolus_request(glucose: i64, target: i64, carbohydrate_grams: i64)
    requires: glucose >= 70 && glucose <= 400 && target >= 80 && target <= 140;
    requires: carbohydrate_grams >= 0 && carbohydrate_grams <= 200;
    ensures: result >= 0;
    ensures: result <= 520;
    body: {
        correction_component(glucose, target) + carbohydrate_component(carbohydrate_grams)
    };

atom hour_capacity(max_dose_per_hour: Units, hour_dosage: Units)
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    ensures: result <= max_dose_per_hour - hour_dosage || hour_dosage > max_dose_per_hour;
    body: {
        floor_at_zero(max_dose_per_hour - hour_dosage)
    };

atom day_capacity(max_dose_per_day: i64, day_dosage: i64)
    requires: max_dose_per_day >= 0 && max_dose_per_day <= 1000;
    requires: day_dosage >= 0 && day_dosage <= 1000;
    ensures: result >= 0;
    ensures: result <= max_dose_per_day;
    body: {
        floor_at_zero(max_dose_per_day - day_dosage)
    };

atom binding_capacity(
    max_dose_per_hour: Units,
    hour_dosage: Units,
    max_dose_per_day: i64,
    day_dosage: i64
)
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    requires: max_dose_per_day >= 0 && max_dose_per_day <= 1000;
    requires: day_dosage >= 0 && day_dosage <= 1000;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    ensures: result <= max_dose_per_day;
    body: {
        smaller_of(
            hour_capacity(max_dose_per_hour, hour_dosage),
            day_capacity(max_dose_per_day, day_dosage)
        )
    };

atom planned_dose(
    glucose: i64,
    target: i64,
    carbohydrate_grams: i64,
    max_dose_per_hour: Units,
    hour_dosage: Units,
    max_dose_per_day: i64,
    day_dosage: i64
)
    requires: glucose >= 70 && glucose <= 400 && target >= 80 && target <= 140;
    requires: carbohydrate_grams >= 0 && carbohydrate_grams <= 200;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    requires: max_dose_per_day >= 0 && max_dose_per_day <= 1000;
    requires: day_dosage >= 0 && day_dosage <= 1000;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    ensures: result <= max_dose_per_day;
    body: {
        smaller_of(
            raw_bolus_request(glucose, target, carbohydrate_grams),
            binding_capacity(max_dose_per_hour, hour_dosage, max_dose_per_day, day_dosage)
        )
    };

// ---------------------------------------------------------------------------
// Layer 3: effectful stages
// ---------------------------------------------------------------------------

atom stage_self_test(battery_percent: Percent, line_pressure: i64)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Idle };
    effect_post: { InsulinPump: SelfTested };
    requires: battery_percent >= 15 && battery_percent <= 100;
    requires: line_pressure >= 0 && line_pressure <= 300;
    ensures: result >= 0 && result <= 1;
    body: {
        perform InsulinPump.self_test;
        all_of_two(battery_sufficient(battery_percent), occlusion_clear(line_pressure))
    };

atom stage_validate_sensors(
    glucose: i64,
    delta_per_minute: i64,
    minutes_since_calibration: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: SelfTested };
    effect_post: { InsulinPump: SensorsValidated };
    requires: glucose >= 70 && glucose <= 400;
    requires: delta_per_minute >= -10 && delta_per_minute <= 10;
    requires: minutes_since_calibration >= 0 && minutes_since_calibration <= 720;
    ensures: result >= 0 && result <= 1;
    body: {
        perform InsulinPump.validate;
        all_of_three(
            glucose_plausible(glucose),
            trend_bounded(delta_per_minute),
            calibration_fresh(minutes_since_calibration)
        )
    };

atom stage_load_profile(reservoir_units: Units, max_dose_per_hour: Units)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: SensorsValidated };
    effect_post: { InsulinPump: ProfileLoaded };
    requires: reservoir_units >= 0 && reservoir_units <= 250;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    body: {
        perform InsulinPump.load_profile;
        smaller_of(reservoir_units, max_dose_per_hour)
    };

atom stage_compute_dose(
    glucose: i64,
    target: i64,
    carbohydrate_grams: i64,
    max_dose_per_hour: Units,
    hour_dosage: Units,
    max_dose_per_day: i64,
    day_dosage: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: ProfileLoaded };
    effect_post: { InsulinPump: DoseComputed };
    requires: glucose >= 70 && glucose <= 400 && target >= 80 && target <= 140;
    requires: carbohydrate_grams >= 0 && carbohydrate_grams <= 200;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    requires: max_dose_per_day >= 0 && max_dose_per_day <= 1000;
    requires: day_dosage >= 0 && day_dosage <= 1000;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    ensures: result <= max_dose_per_day;
    body: {
        perform InsulinPump.compute;
        planned_dose(
            glucose,
            target,
            carbohydrate_grams,
            max_dose_per_hour,
            hour_dosage,
            max_dose_per_day,
            day_dosage
        )
    };

atom stage_check_limits(planned_units: Units, max_dose_per_hour: Units, hour_dosage: Units)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: DoseComputed };
    effect_post: { InsulinPump: LimitsChecked };
    requires: planned_units >= 0 && planned_units <= 250;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    ensures: result <= planned_units;
    body: {
        perform InsulinPump.check_limits;
        smaller_of(planned_units, hour_capacity(max_dose_per_hour, hour_dosage))
    };

atom stage_arm_interlock(approved_units: Units, reservoir_units: Units)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: LimitsChecked };
    effect_post: { InsulinPump: InterlockArmed };
    requires: approved_units >= 0 && approved_units <= 250;
    requires: reservoir_units >= 0 && reservoir_units <= 250;
    ensures: result >= 0;
    ensures: result <= approved_units;
    ensures: result <= reservoir_units;
    body: {
        perform InsulinPump.arm;
        smaller_of(approved_units, reservoir_units)
    };

atom stage_deliver(armed_units: Units, max_dose_per_hour: Units, hour_dosage: Units)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: InterlockArmed };
    effect_post: { InsulinPump: Delivered };
    requires: armed_units >= 0 && armed_units <= 250;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    ensures: result >= 0;
    ensures: result <= armed_units;
    ensures: result <= max_dose_per_hour;
    body: {
        perform InsulinPump.deliver;
        smaller_of(armed_units, hour_capacity(max_dose_per_hour, hour_dosage))
    };

atom stage_journal(delivered_units: Units)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Delivered };
    effect_post: { InsulinPump: Delivered };
    requires: delivered_units >= 0 && delivered_units <= 250;
    ensures: result >= 0;
    ensures: result <= delivered_units;
    body: {
        perform InsulinPump.journal;
        delivered_units
    };

atom stage_reset(journaled_units: Units)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Delivered };
    effect_post: { InsulinPump: Idle };
    requires: journaled_units >= 0 && journaled_units <= 250;
    ensures: result >= 0;
    ensures: result <= journaled_units;
    body: {
        perform InsulinPump.reset;
        journaled_units
    };

// ---------------------------------------------------------------------------
// Layer 4: phases
// ---------------------------------------------------------------------------

atom phase_prepare(
    battery_percent: Percent,
    line_pressure: i64,
    glucose: i64,
    delta_per_minute: i64,
    minutes_since_calibration: i64,
    reservoir_units: Units,
    max_dose_per_hour: Units
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Idle };
    effect_post: { InsulinPump: ProfileLoaded };
    requires: battery_percent >= 15 && battery_percent <= 100;
    requires: line_pressure >= 0 && line_pressure <= 300;
    requires: glucose >= 70 && glucose <= 400;
    requires: delta_per_minute >= -10 && delta_per_minute <= 10;
    requires: minutes_since_calibration >= 0 && minutes_since_calibration <= 720;
    requires: reservoir_units >= 0 && reservoir_units <= 250;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    body: {
        stage_self_test(battery_percent, line_pressure);
        stage_validate_sensors(glucose, delta_per_minute, minutes_since_calibration);
        stage_load_profile(reservoir_units, max_dose_per_hour)
    };

atom phase_plan(
    glucose: i64,
    target: i64,
    carbohydrate_grams: i64,
    max_dose_per_hour: Units,
    hour_dosage: Units,
    max_dose_per_day: i64,
    day_dosage: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: ProfileLoaded };
    effect_post: { InsulinPump: LimitsChecked };
    requires: glucose >= 70 && glucose <= 400 && target >= 80 && target <= 140;
    requires: carbohydrate_grams >= 0 && carbohydrate_grams <= 200;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    requires: max_dose_per_day >= 0 && max_dose_per_day <= 1000;
    requires: day_dosage >= 0 && day_dosage <= 1000;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    body: {
        let planned = stage_compute_dose(
            glucose,
            target,
            carbohydrate_grams,
            max_dose_per_hour,
            hour_dosage,
            max_dose_per_day,
            day_dosage
        );
        stage_check_limits(planned, max_dose_per_hour, hour_dosage)
    };

atom phase_commit(
    approved_units: Units,
    reservoir_units: Units,
    max_dose_per_hour: Units,
    hour_dosage: Units
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: LimitsChecked };
    effect_post: { InsulinPump: Delivered };
    requires: approved_units >= 0 && approved_units <= 250;
    requires: reservoir_units >= 0 && reservoir_units <= 250;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    ensures: result >= 0;
    ensures: result <= approved_units;
    ensures: result <= max_dose_per_hour;
    body: {
        let armed = stage_arm_interlock(approved_units, reservoir_units);
        stage_deliver(armed, max_dose_per_hour, hour_dosage)
    };

atom phase_close(delivered_units: Units)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Delivered };
    effect_post: { InsulinPump: Idle };
    requires: delivered_units >= 0 && delivered_units <= 250;
    ensures: result >= 0;
    ensures: result <= delivered_units;
    body: {
        let journaled = stage_journal(delivered_units);
        stage_reset(journaled)
    };

// ---------------------------------------------------------------------------
// Layer 5: whole therapy cycles
// ---------------------------------------------------------------------------

atom therapy_cycle(
    battery_percent: Percent,
    line_pressure: i64,
    glucose: i64,
    delta_per_minute: i64,
    minutes_since_calibration: i64,
    reservoir_units: Units,
    target: i64,
    carbohydrate_grams: i64,
    max_dose_per_hour: Units,
    hour_dosage: Units,
    max_dose_per_day: i64,
    day_dosage: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Idle };
    effect_post: { InsulinPump: Idle };
    requires: battery_percent >= 15 && battery_percent <= 100;
    requires: line_pressure >= 0 && line_pressure <= 300;
    requires: glucose >= 70 && glucose <= 400 && target >= 80 && target <= 140;
    requires: delta_per_minute >= -10 && delta_per_minute <= 10;
    requires: minutes_since_calibration >= 0 && minutes_since_calibration <= 720;
    requires: reservoir_units >= 0 && reservoir_units <= 250;
    requires: carbohydrate_grams >= 0 && carbohydrate_grams <= 200;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    requires: max_dose_per_day >= 0 && max_dose_per_day <= 1000;
    requires: day_dosage >= 0 && day_dosage <= 1000;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    body: {
        phase_prepare(
            battery_percent,
            line_pressure,
            glucose,
            delta_per_minute,
            minutes_since_calibration,
            reservoir_units,
            max_dose_per_hour
        );
        let approved = phase_plan(
            glucose,
            target,
            carbohydrate_grams,
            max_dose_per_hour,
            hour_dosage,
            max_dose_per_day,
            day_dosage
        );
        let delivered = phase_commit(approved, reservoir_units, max_dose_per_hour, hour_dosage);
        phase_close(delivered)
    };

atom two_therapy_cycles(
    battery_percent: Percent,
    line_pressure: i64,
    glucose: i64,
    delta_per_minute: i64,
    minutes_since_calibration: i64,
    reservoir_units: Units,
    target: i64,
    carbohydrate_grams: i64,
    max_dose_per_hour: Units,
    hour_dosage: Units,
    max_dose_per_day: i64,
    day_dosage: i64
)
    effects: [InsulinPump];
    effect_pre: { InsulinPump: Idle };
    effect_post: { InsulinPump: Idle };
    requires: battery_percent >= 15 && battery_percent <= 100;
    requires: line_pressure >= 0 && line_pressure <= 300;
    requires: glucose >= 70 && glucose <= 400 && target >= 80 && target <= 140;
    requires: delta_per_minute >= -10 && delta_per_minute <= 10;
    requires: minutes_since_calibration >= 0 && minutes_since_calibration <= 720;
    requires: reservoir_units >= 0 && reservoir_units <= 250;
    requires: carbohydrate_grams >= 0 && carbohydrate_grams <= 200;
    requires: max_dose_per_hour >= 0 && max_dose_per_hour <= 250;
    requires: hour_dosage >= 0 && hour_dosage <= 250;
    requires: max_dose_per_day >= 0 && max_dose_per_day <= 1000;
    requires: day_dosage >= 0 && day_dosage <= 1000;
    ensures: result >= 0;
    ensures: result <= max_dose_per_hour;
    body: {
        therapy_cycle(
            battery_percent,
            line_pressure,
            glucose,
            delta_per_minute,
            minutes_since_calibration,
            reservoir_units,
            target,
            carbohydrate_grams,
            max_dose_per_hour,
            hour_dosage,
            max_dose_per_day,
            day_dosage
        );
        therapy_cycle(
            battery_percent,
            line_pressure,
            glucose,
            delta_per_minute,
            minutes_since_calibration,
            reservoir_units,
            target,
            carbohydrate_grams,
            max_dose_per_hour,
            hour_dosage,
            max_dose_per_day,
            day_dosage
        )
    };
