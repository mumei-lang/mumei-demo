// RegTech compliance at operational scale: twelve independent rules, five rule
// groups, a bounded risk score and an eight-state review workflow.
// Priority 16 large-scale case: the combinatorial explosion of rule
// conjunctions is discharged atom-locally — every combinator only sees the
// ensures of its immediate operands, never the global compliance predicate.

type Score = i64 where v >= 0 && v <= 100;
type Flag = i64 where v >= 0 && v <= 1;

effect ComplianceReview
    states: [
        Idle,
        Intake,
        Screened,
        Scored,
        RulesApplied,
        Decided,
        Reported,
        Archived
    ];
    initial: Idle;
    transition intake: Idle -> Intake;
    transition screen: Intake -> Screened;
    transition score: Screened -> Scored;
    transition apply_rules: Scored -> RulesApplied;
    transition decide: RulesApplied -> Decided;
    transition report: Decided -> Reported;
    transition archive: Reported -> Archived;
    transition reset: Archived -> Idle;
    transition abort: Intake -> Idle;

// ---------------------------------------------------------------------------
// Layer 0: rule combinators
// ---------------------------------------------------------------------------

atom rule_and(left: Flag, right: Flag)
    requires: left >= 0 && left <= 1;
    requires: right >= 0 && right <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || left == 1;
    ensures: result == 0 || right == 1;
    body: {
        if left == 1 && right == 1 { 1 } else { 0 }
    };

atom rule_or(left: Flag, right: Flag)
    requires: left >= 0 && left <= 1;
    requires: right >= 0 && right <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 1 || left == 0;
    ensures: result == 1 || right == 0;
    body: {
        if left == 1 || right == 1 { 1 } else { 0 }
    };

atom rule_implies(premise: Flag, conclusion: Flag)
    requires: premise >= 0 && premise <= 1;
    requires: conclusion >= 0 && conclusion <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 1 || premise == 1;
    ensures: result == 1 || conclusion == 0;
    body: {
        if premise == 0 || conclusion == 1 { 1 } else { 0 }
    };

atom rule_and3(first: Flag, second: Flag, third: Flag)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1;
    requires: third >= 0 && third <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || first == 1;
    ensures: result == 0 || third == 1;
    body: {
        rule_and(rule_and(first, second), third)
    };

atom rule_and4(first: Flag, second: Flag, third: Flag, fourth: Flag)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1;
    requires: third >= 0 && third <= 1 && fourth >= 0 && fourth <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || first == 1;
    ensures: result == 0 || fourth == 1;
    body: {
        rule_and(rule_and3(first, second, third), fourth)
    };

atom rule_and5(first: Flag, second: Flag, third: Flag, fourth: Flag, fifth: Flag)
    requires: first >= 0 && first <= 1 && second >= 0 && second <= 1;
    requires: third >= 0 && third <= 1 && fourth >= 0 && fourth <= 1;
    requires: fifth >= 0 && fifth <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || first == 1;
    ensures: result == 0 || fifth == 1;
    body: {
        rule_and(rule_and4(first, second, third, fourth), fifth)
    };

// ---------------------------------------------------------------------------
// Layer 1: individual compliance rules
// ---------------------------------------------------------------------------

atom kyc_documents_verified(document_state: i64)
    requires: document_state >= 0 && document_state <= 4;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || document_state == 2;
    body: {
        if document_state == 2 { 1 } else { 0 }
    };

atom identity_reverified_recently(days_since_review: i64)
    requires: days_since_review >= 0 && days_since_review <= 3650;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || days_since_review <= 365;
    body: {
        if days_since_review <= 365 { 1 } else { 0 }
    };

atom beneficial_owner_disclosed(owner_count: i64, disclosed_count: i64)
    requires: owner_count >= 0 && owner_count <= 50;
    requires: disclosed_count >= 0 && disclosed_count <= 50;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || disclosed_count >= owner_count;
    body: {
        if disclosed_count >= owner_count { 1 } else { 0 }
    };

atom sanctions_screening_clear(hit_count: i64)
    requires: hit_count >= 0 && hit_count <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || hit_count == 0;
    body: {
        if hit_count == 0 { 1 } else { 0 }
    };

atom pep_exposure_reviewed(pep_flag: Flag, review_flag: Flag)
    requires: pep_flag >= 0 && pep_flag <= 1;
    requires: review_flag >= 0 && review_flag <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 1 || pep_flag == 1;
    body: {
        rule_implies(pep_flag, review_flag)
    };

atom adverse_media_cleared(open_alerts: i64)
    requires: open_alerts >= 0 && open_alerts <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || open_alerts == 0;
    body: {
        if open_alerts == 0 { 1 } else { 0 }
    };

atom jurisdiction_permitted(jurisdiction_tier: i64)
    requires: jurisdiction_tier >= 0 && jurisdiction_tier <= 5;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || jurisdiction_tier <= 2;
    body: {
        if jurisdiction_tier <= 2 { 1 } else { 0 }
    };

atom license_in_force(license_state: i64)
    requires: license_state >= 0 && license_state <= 3;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || license_state == 1;
    body: {
        if license_state == 1 { 1 } else { 0 }
    };

atom threshold_report_filed(amount: i64, filed_flag: Flag)
    requires: amount >= 0 && amount <= 100000000;
    requires: filed_flag >= 0 && filed_flag <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 1 || amount > 1000000;
    body: {
        if amount <= 1000000 || filed_flag == 1 { 1 } else { 0 }
    };

atom retention_period_satisfied(retention_years: i64)
    requires: retention_years >= 0 && retention_years <= 50;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || retention_years >= 5;
    body: {
        if retention_years >= 5 { 1 } else { 0 }
    };

atom data_processing_consented(consent_state: i64)
    requires: consent_state >= 0 && consent_state <= 2;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || consent_state == 1;
    body: {
        if consent_state == 1 { 1 } else { 0 }
    };

atom audit_trail_complete(missing_events: i64)
    requires: missing_events >= 0 && missing_events <= 1000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || missing_events == 0;
    body: {
        if missing_events == 0 { 1 } else { 0 }
    };

// ---------------------------------------------------------------------------
// Layer 2: rule groups
// ---------------------------------------------------------------------------

atom group_kyc(document_state: i64, days_since_review: i64, owner_count: i64, disclosed_count: i64)
    requires: document_state >= 0 && document_state <= 4;
    requires: days_since_review >= 0 && days_since_review <= 3650;
    requires: owner_count >= 0 && owner_count <= 50;
    requires: disclosed_count >= 0 && disclosed_count <= 50;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || document_state == 2;
    body: {
        rule_and3(
            kyc_documents_verified(document_state),
            identity_reverified_recently(days_since_review),
            beneficial_owner_disclosed(owner_count, disclosed_count)
        )
    };

atom group_aml(hit_count: i64, pep_flag: Flag, review_flag: Flag, open_alerts: i64)
    requires: hit_count >= 0 && hit_count <= 100;
    requires: pep_flag >= 0 && pep_flag <= 1 && review_flag >= 0 && review_flag <= 1;
    requires: open_alerts >= 0 && open_alerts <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || hit_count == 0;
    body: {
        rule_and3(
            sanctions_screening_clear(hit_count),
            pep_exposure_reviewed(pep_flag, review_flag),
            adverse_media_cleared(open_alerts)
        )
    };

atom group_market_access(jurisdiction_tier: i64, license_state: i64)
    requires: jurisdiction_tier >= 0 && jurisdiction_tier <= 5;
    requires: license_state >= 0 && license_state <= 3;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || jurisdiction_tier <= 2;
    ensures: result == 0 || license_state == 1;
    body: {
        rule_and(
            jurisdiction_permitted(jurisdiction_tier),
            license_in_force(license_state)
        )
    };

atom group_reporting(amount: i64, filed_flag: Flag, retention_years: i64)
    requires: amount >= 0 && amount <= 100000000;
    requires: filed_flag >= 0 && filed_flag <= 1;
    requires: retention_years >= 0 && retention_years <= 50;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || retention_years >= 5;
    body: {
        rule_and(
            threshold_report_filed(amount, filed_flag),
            retention_period_satisfied(retention_years)
        )
    };

atom group_data_governance(consent_state: i64, missing_events: i64)
    requires: consent_state >= 0 && consent_state <= 2;
    requires: missing_events >= 0 && missing_events <= 1000;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || consent_state == 1;
    ensures: result == 0 || missing_events == 0;
    body: {
        rule_and(
            data_processing_consented(consent_state),
            audit_trail_complete(missing_events)
        )
    };

// ---------------------------------------------------------------------------
// Layer 3: bounded risk scoring
// ---------------------------------------------------------------------------

atom clamp_score(value: i64)
    requires: value >= -1000 && value <= 1000;
    ensures: result >= 0 && result <= 100;
    body: {
        if value < 0 { 0 } else { if value > 100 { 100 } else { value } }
    };

atom inherent_risk(jurisdiction_tier: i64, pep_flag: Flag, hit_count: i64)
    requires: jurisdiction_tier >= 0 && jurisdiction_tier <= 5;
    requires: pep_flag >= 0 && pep_flag <= 1;
    requires: hit_count >= 0 && hit_count <= 100;
    ensures: result >= 0 && result <= 100;
    body: {
        clamp_score(jurisdiction_tier * 10 + pep_flag * 20 + hit_count)
    };

atom control_offset(kyc_ok: Flag, aml_ok: Flag, data_ok: Flag)
    requires: kyc_ok >= 0 && kyc_ok <= 1 && aml_ok >= 0 && aml_ok <= 1;
    requires: data_ok >= 0 && data_ok <= 1;
    ensures: result >= 0 && result <= 100;
    body: {
        clamp_score(kyc_ok * 15 + aml_ok * 15 + data_ok * 10)
    };

atom residual_risk(inherent: Score, offset: Score)
    requires: inherent >= 0 && inherent <= 100;
    requires: offset >= 0 && offset <= 100;
    ensures: result >= 0 && result <= 100;
    ensures: result <= inherent;
    body: {
        if inherent - offset < 0 { 0 } else { inherent - offset }
    };

atom risk_within_appetite(residual: Score, appetite: Score)
    requires: residual >= 0 && residual <= 100;
    requires: appetite >= 0 && appetite <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || residual <= appetite;
    body: {
        if residual <= appetite { 1 } else { 0 }
    };

// ---------------------------------------------------------------------------
// Layer 4: effectful review stages
// ---------------------------------------------------------------------------

atom stage_intake(document_state: i64, days_since_review: i64, owner_count: i64, disclosed_count: i64)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Idle };
    effect_post: { ComplianceReview: Intake };
    requires: document_state >= 0 && document_state <= 4;
    requires: days_since_review >= 0 && days_since_review <= 3650;
    requires: owner_count >= 0 && owner_count <= 50;
    requires: disclosed_count >= 0 && disclosed_count <= 50;
    ensures: result >= 0 && result <= 1;
    body: {
        perform ComplianceReview.intake;
        group_kyc(document_state, days_since_review, owner_count, disclosed_count)
    };

atom stage_screen(hit_count: i64, pep_flag: Flag, review_flag: Flag, open_alerts: i64)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Intake };
    effect_post: { ComplianceReview: Screened };
    requires: hit_count >= 0 && hit_count <= 100;
    requires: pep_flag >= 0 && pep_flag <= 1 && review_flag >= 0 && review_flag <= 1;
    requires: open_alerts >= 0 && open_alerts <= 100;
    ensures: result >= 0 && result <= 1;
    body: {
        perform ComplianceReview.screen;
        group_aml(hit_count, pep_flag, review_flag, open_alerts)
    };

atom stage_score(
    jurisdiction_tier: i64,
    pep_flag: Flag,
    hit_count: i64,
    kyc_ok: Flag,
    aml_ok: Flag,
    data_ok: Flag
)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Screened };
    effect_post: { ComplianceReview: Scored };
    requires: jurisdiction_tier >= 0 && jurisdiction_tier <= 5;
    requires: pep_flag >= 0 && pep_flag <= 1 && hit_count >= 0 && hit_count <= 100;
    requires: kyc_ok >= 0 && kyc_ok <= 1 && aml_ok >= 0 && aml_ok <= 1;
    requires: data_ok >= 0 && data_ok <= 1;
    ensures: result >= 0 && result <= 100;
    body: {
        perform ComplianceReview.score;
        let inherent = inherent_risk(jurisdiction_tier, pep_flag, hit_count);
        let offset = control_offset(kyc_ok, aml_ok, data_ok);
        residual_risk(inherent, offset)
    };

atom stage_apply_rules(
    kyc_ok: Flag,
    aml_ok: Flag,
    market_ok: Flag,
    reporting_ok: Flag,
    data_ok: Flag
)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Scored };
    effect_post: { ComplianceReview: RulesApplied };
    requires: kyc_ok >= 0 && kyc_ok <= 1 && aml_ok >= 0 && aml_ok <= 1;
    requires: market_ok >= 0 && market_ok <= 1 && reporting_ok >= 0 && reporting_ok <= 1;
    requires: data_ok >= 0 && data_ok <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || kyc_ok == 1;
    ensures: result == 0 || data_ok == 1;
    body: {
        perform ComplianceReview.apply_rules;
        rule_and5(kyc_ok, aml_ok, market_ok, reporting_ok, data_ok)
    };

atom stage_decide(rules_ok: Flag, residual: Score, appetite: Score)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: RulesApplied };
    effect_post: { ComplianceReview: Decided };
    requires: rules_ok >= 0 && rules_ok <= 1;
    requires: residual >= 0 && residual <= 100;
    requires: appetite >= 0 && appetite <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || rules_ok == 1;
    body: {
        perform ComplianceReview.decide;
        rule_and(rules_ok, risk_within_appetite(residual, appetite))
    };

atom stage_report(decision: Flag, amount: i64, filed_flag: Flag)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Decided };
    effect_post: { ComplianceReview: Reported };
    requires: decision >= 0 && decision <= 1;
    requires: amount >= 0 && amount <= 100000000;
    requires: filed_flag >= 0 && filed_flag <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || decision == 1;
    body: {
        perform ComplianceReview.report;
        rule_and(decision, threshold_report_filed(amount, filed_flag))
    };

atom stage_archive(outcome: Flag, retention_years: i64)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Reported };
    effect_post: { ComplianceReview: Archived };
    requires: outcome >= 0 && outcome <= 1;
    requires: retention_years >= 0 && retention_years <= 50;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || outcome == 1;
    body: {
        perform ComplianceReview.archive;
        rule_and(outcome, retention_period_satisfied(retention_years))
    };

atom stage_reset(outcome: Flag)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Archived };
    effect_post: { ComplianceReview: Idle };
    requires: outcome >= 0 && outcome <= 1;
    ensures: result >= 0 && result <= 1;
    ensures: result == outcome;
    body: {
        perform ComplianceReview.reset;
        outcome
    };

// ---------------------------------------------------------------------------
// Layer 5: phases
// ---------------------------------------------------------------------------

atom phase_onboarding(
    document_state: i64,
    days_since_review: i64,
    owner_count: i64,
    disclosed_count: i64,
    hit_count: i64,
    pep_flag: Flag,
    review_flag: Flag,
    open_alerts: i64
)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Idle };
    effect_post: { ComplianceReview: Screened };
    requires: document_state >= 0 && document_state <= 4;
    requires: days_since_review >= 0 && days_since_review <= 3650;
    requires: owner_count >= 0 && owner_count <= 50 && disclosed_count >= 0 && disclosed_count <= 50;
    requires: hit_count >= 0 && hit_count <= 100;
    requires: pep_flag >= 0 && pep_flag <= 1 && review_flag >= 0 && review_flag <= 1;
    requires: open_alerts >= 0 && open_alerts <= 100;
    ensures: result >= 0 && result <= 1;
    body: {
        stage_intake(document_state, days_since_review, owner_count, disclosed_count);
        stage_screen(hit_count, pep_flag, review_flag, open_alerts)
    };

atom phase_assessment(
    jurisdiction_tier: i64,
    pep_flag: Flag,
    hit_count: i64,
    kyc_ok: Flag,
    aml_ok: Flag,
    market_ok: Flag,
    reporting_ok: Flag,
    data_ok: Flag,
    appetite: Score
)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Screened };
    effect_post: { ComplianceReview: Decided };
    requires: jurisdiction_tier >= 0 && jurisdiction_tier <= 5;
    requires: pep_flag >= 0 && pep_flag <= 1 && hit_count >= 0 && hit_count <= 100;
    requires: kyc_ok >= 0 && kyc_ok <= 1 && aml_ok >= 0 && aml_ok <= 1;
    requires: market_ok >= 0 && market_ok <= 1 && reporting_ok >= 0 && reporting_ok <= 1;
    requires: data_ok >= 0 && data_ok <= 1;
    requires: appetite >= 0 && appetite <= 100;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || kyc_ok == 1;
    body: {
        let residual = stage_score(jurisdiction_tier, pep_flag, hit_count, kyc_ok, aml_ok, data_ok);
        let rules_ok = stage_apply_rules(kyc_ok, aml_ok, market_ok, reporting_ok, data_ok);
        stage_decide(rules_ok, residual, appetite)
    };

atom phase_disposition(decision: Flag, amount: i64, filed_flag: Flag, retention_years: i64)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Decided };
    effect_post: { ComplianceReview: Idle };
    requires: decision >= 0 && decision <= 1;
    requires: amount >= 0 && amount <= 100000000;
    requires: filed_flag >= 0 && filed_flag <= 1;
    requires: retention_years >= 0 && retention_years <= 50;
    ensures: result >= 0 && result <= 1;
    ensures: result == 0 || decision == 1;
    body: {
        let reported = stage_report(decision, amount, filed_flag);
        let archived = stage_archive(reported, retention_years);
        stage_reset(archived)
    };

// ---------------------------------------------------------------------------
// Layer 6: whole review cycles
// ---------------------------------------------------------------------------

atom compliance_cycle(
    document_state: i64,
    days_since_review: i64,
    owner_count: i64,
    disclosed_count: i64,
    hit_count: i64,
    pep_flag: Flag,
    review_flag: Flag,
    open_alerts: i64,
    jurisdiction_tier: i64,
    license_state: i64,
    amount: i64,
    filed_flag: Flag,
    retention_years: i64,
    consent_state: i64,
    missing_events: i64,
    appetite: Score
)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Idle };
    effect_post: { ComplianceReview: Idle };
    requires: document_state >= 0 && document_state <= 4;
    requires: days_since_review >= 0 && days_since_review <= 3650;
    requires: owner_count >= 0 && owner_count <= 50 && disclosed_count >= 0 && disclosed_count <= 50;
    requires: hit_count >= 0 && hit_count <= 100;
    requires: pep_flag >= 0 && pep_flag <= 1 && review_flag >= 0 && review_flag <= 1;
    requires: open_alerts >= 0 && open_alerts <= 100;
    requires: jurisdiction_tier >= 0 && jurisdiction_tier <= 5;
    requires: license_state >= 0 && license_state <= 3;
    requires: amount >= 0 && amount <= 100000000;
    requires: filed_flag >= 0 && filed_flag <= 1;
    requires: retention_years >= 0 && retention_years <= 50;
    requires: consent_state >= 0 && consent_state <= 2;
    requires: missing_events >= 0 && missing_events <= 1000;
    requires: appetite >= 0 && appetite <= 100;
    ensures: result >= 0 && result <= 1;
    body: {
        let kyc_ok = group_kyc(document_state, days_since_review, owner_count, disclosed_count);
        let aml_ok = group_aml(hit_count, pep_flag, review_flag, open_alerts);
        let market_ok = group_market_access(jurisdiction_tier, license_state);
        let reporting_ok = group_reporting(amount, filed_flag, retention_years);
        let data_ok = group_data_governance(consent_state, missing_events);
        phase_onboarding(
            document_state,
            days_since_review,
            owner_count,
            disclosed_count,
            hit_count,
            pep_flag,
            review_flag,
            open_alerts
        );
        let decision = phase_assessment(
            jurisdiction_tier,
            pep_flag,
            hit_count,
            kyc_ok,
            aml_ok,
            market_ok,
            reporting_ok,
            data_ok,
            appetite
        );
        phase_disposition(decision, amount, filed_flag, retention_years)
    };

atom two_compliance_cycles(
    document_state: i64,
    days_since_review: i64,
    owner_count: i64,
    disclosed_count: i64,
    hit_count: i64,
    pep_flag: Flag,
    review_flag: Flag,
    open_alerts: i64,
    jurisdiction_tier: i64,
    license_state: i64,
    amount: i64,
    filed_flag: Flag,
    retention_years: i64,
    consent_state: i64,
    missing_events: i64,
    appetite: Score
)
    effects: [ComplianceReview];
    effect_pre: { ComplianceReview: Idle };
    effect_post: { ComplianceReview: Idle };
    requires: document_state >= 0 && document_state <= 4;
    requires: days_since_review >= 0 && days_since_review <= 3650;
    requires: owner_count >= 0 && owner_count <= 50 && disclosed_count >= 0 && disclosed_count <= 50;
    requires: hit_count >= 0 && hit_count <= 100;
    requires: pep_flag >= 0 && pep_flag <= 1 && review_flag >= 0 && review_flag <= 1;
    requires: open_alerts >= 0 && open_alerts <= 100;
    requires: jurisdiction_tier >= 0 && jurisdiction_tier <= 5;
    requires: license_state >= 0 && license_state <= 3;
    requires: amount >= 0 && amount <= 100000000;
    requires: filed_flag >= 0 && filed_flag <= 1;
    requires: retention_years >= 0 && retention_years <= 50;
    requires: consent_state >= 0 && consent_state <= 2;
    requires: missing_events >= 0 && missing_events <= 1000;
    requires: appetite >= 0 && appetite <= 100;
    ensures: result >= 0 && result <= 1;
    body: {
        compliance_cycle(
            document_state,
            days_since_review,
            owner_count,
            disclosed_count,
            hit_count,
            pep_flag,
            review_flag,
            open_alerts,
            jurisdiction_tier,
            license_state,
            amount,
            filed_flag,
            retention_years,
            consent_state,
            missing_events,
            appetite
        );
        compliance_cycle(
            document_state,
            days_since_review,
            owner_count,
            disclosed_count,
            hit_count,
            pep_flag,
            review_flag,
            open_alerts,
            jurisdiction_tier,
            license_state,
            amount,
            filed_flag,
            retention_years,
            consent_state,
            missing_events,
            appetite
        )
    };
