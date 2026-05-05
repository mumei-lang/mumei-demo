// ❌ Intentionally buggy implementation template
// Copy this file into a new scenario and replace the effect, atom names, and
// violated transition/property with your concrete demo bug.

effect ScenarioState
    states: [Initial, Checked, Complete];
    initial: Initial;
    transition check: Initial -> Checked;
    transition complete: Checked -> Complete;

atom buggy_flow(input: i64)
    effects: [ScenarioState];
    effect_pre: { ScenarioState: Initial };
    effect_post: { ScenarioState: Complete };
    requires: input >= 0;
    ensures: result == input;
    body: {
        // BUG: skips ScenarioState.check and tries to complete too early.
        perform ScenarioState.complete;
        input
    };
