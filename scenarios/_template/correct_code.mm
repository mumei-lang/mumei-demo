// ✅ Correct implementation template
// Copy this file into a new scenario and encode the safe path that satisfies
// the same contract the buggy implementation violated.

effect ScenarioState
    states: [Initial, Checked, Complete];
    initial: Initial;
    transition check: Initial -> Checked;
    transition complete: Checked -> Complete;

atom check_input(input: i64)
    effects: [ScenarioState];
    effect_pre: { ScenarioState: Initial };
    effect_post: { ScenarioState: Checked };
    requires: input >= 0;
    ensures: result == input;
    body: {
        perform ScenarioState.check;
        input
    };

atom complete_flow(input: i64)
    effects: [ScenarioState];
    effect_pre: { ScenarioState: Checked };
    effect_post: { ScenarioState: Complete };
    requires: input >= 0;
    ensures: result == input;
    body: {
        perform ScenarioState.complete;
        input
    };

atom safe_flow(input: i64)
    effects: [ScenarioState];
    effect_pre: { ScenarioState: Initial };
    effect_post: { ScenarioState: Complete };
    requires: input >= 0;
    ensures: result == input;
    body: {
        check_input(input);
        complete_flow(input)
    };
