SCENARIOS := ownership_transfer rtgs_settlement regtech_compliance nl_to_verified no_mm_audit spec_code_verification_suite mumei_develop_audit smart_contract_audit blockchain_audit medical_device aviation_control merkle_tree_verification defi_invariant arklib_style_audit charter_gate_demo negative_controls_demo test_observation_demo self_correction_demo
# Large-scale (Priority 16) targets. Kept out of SCENARIOS on purpose: they are
# separate targets so the deterministic fixture-mode CI run stays unchanged.
SCALE_SCENARIOS := medical_device_scale rtgs_settlement_scale regtech_compliance_scale defi_invariant_scale ownership_transfer_scale
OPTIONAL_SCENARIOS := record_execution_demo go_summaries ts_summaries rust_summaries sol_summaries audit_summaries translation_validation verify_recheck verify_attempt native_recheck evidence_identity evidence_check_accept evidence_compare native_attempt native_check native_artifact_recheck native_refined_attempt native_refined_widened_attempt verify_accept evidence_check_attempt_acceptance evidence_check_list evidence_check_consistency native_accept native_evidence_recheck native_evidence_accept native_source_recheck native_exit_status_recheck native_exit_status_accept native_stdout_recheck native_stdout_accept native_stderr_recheck native_stderr_accept native_observations_accept native_observations_recheck native_object_recheck native_machine_tv_recheck evidence_check_schedule native_observations_recovery native_composite_attempt evidence_check summaries_plan summaries_attempt evidence_producer producer_signature_recovery agent_signature_sign claimbook_acceptance_gate schedule_export_gate
NO_MM_AUDIT_LANGUAGES := python rust typescript go
MUMEI_REPO ?= ../mumei
MUMEI_AGENT_REPO ?= ../mumei-agent

.PHONY: demo demo-ownership demo-settlement demo-regtech demo-nl demo-no-mm demo-no-mm-multilang demo-spec-code demo-mumei-develop-audit demo-smart-contract demo-blockchain demo-medical demo-aviation demo-merkle demo-defi demo-arklib demo-charter demo-negative-controls demo-test-observation demo-self-correction demo-human-review demo-all demo-ci report setup help \
	demo-scale demo-medical-scale demo-settlement-scale demo-regtech-scale demo-defi-scale demo-ownership-scale \
	demo-go-summaries demo-ts-summaries demo-rust-summaries demo-sol-summaries demo-audit-summaries \
	demo-translation-validation demo-verify-recheck demo-verify-attempt demo-native-recheck demo-evidence-check-attempt-acceptance demo-evidence-identity demo-evidence-check-accept demo-evidence-compare demo-native-attempt demo-native-refined-attempt demo-native-refined-widened-attempt demo-evidence-check demo-summaries-plan demo-summaries-attempt demo-evidence-producer demo-producer-signature-recovery demo-agent-signature-sign demo-claimbook-acceptance-gate demo-schedule-export-gate

demo: ## Run the default scenario set and regenerate summary reports.
	@status=0; \
	for scenario in $(SCENARIOS); do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	$(MAKE) report || status=1; \
	exit "$$status"


help: ## List Make targets and their descriptions.
	@awk 'BEGIN { FS = ":.*##" } /^[[:alnum:]_.-]+:.*##/ { printf "  %-30s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

demo-ownership: ## Run ownership-transfer verification.
	@./scripts/run_scenario.sh ownership_transfer

demo-settlement: ## Run real-time settlement verification.
	@./scripts/run_scenario.sh rtgs_settlement

demo-regtech: ## Run RegTech compliance verification.
	@./scripts/run_scenario.sh regtech_compliance

demo-nl: ## Natural-language spec -> verified code (fixture mode unless CI_FIXTURE_MODE=0).
	@mode="$${CI_FIXTURE_MODE:-1}"; \
	if [ "$$mode" = "1" ]; then \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh nl_to_verified; \
	else \
		./scripts/run_scenario.sh nl_to_verified; \
	fi
	@python3 scripts/generate_report.py reports/nl_to_verified/latest/result.json --format markdown --report-output reports/nl_to_verified/latest/report.md
	@python3 dashboard/cli_report.py reports/nl_to_verified/latest/result.json

demo-no-mm: ## Audit existing code without .mm files in the configured languages.
	@mode="$${CI_FIXTURE_MODE:-1}"; \
	if [ "$$mode" = "1" ]; then \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh no_mm_audit \
			--mumei-repo "$(MUMEI_REPO)" \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	else \
		./scripts/run_scenario.sh no_mm_audit \
			--mumei-repo "$(MUMEI_REPO)" \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	fi
	@echo "no_mm_audit languages: $(NO_MM_AUDIT_LANGUAGES)"

demo-no-mm-multilang: demo-no-mm ## Alias for the multi-language no-.mm audit.

demo-spec-code: ## Run the spec-to-verified-code scenario suite.
	@mode="$${CI_FIXTURE_MODE:-1}"; \
	if [ "$$mode" = "1" ]; then \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh spec_code_verification_suite \
			--mumei-repo "$(MUMEI_REPO)" \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	else \
		./scripts/run_scenario.sh spec_code_verification_suite \
			--mumei-repo "$(MUMEI_REPO)" \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	fi

demo-mumei-develop-audit: ## Audit the sibling mumei develop checkout.
	@mode="$${CI_FIXTURE_MODE:-1}"; \
	if [ "$$mode" = "1" ]; then \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh mumei_develop_audit \
			--mumei-repo "$(MUMEI_REPO)" \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	else \
		./scripts/run_scenario.sh mumei_develop_audit \
			--mumei-repo "$(MUMEI_REPO)" \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	fi

demo-smart-contract: ## Run the smart-contract audit.
	@./scripts/run_scenario.sh smart_contract_audit

demo-blockchain: ## Run the blockchain audit.
	@./scripts/run_blockchain_audit.sh

demo-medical: ## Run medical-device verification.
	@./scripts/run_scenario.sh medical_device

demo-aviation: ## Run aviation-control verification.
	@./scripts/run_scenario.sh aviation_control

demo-merkle: ## Run Merkle-tree verification.
	@./scripts/run_scenario.sh merkle_tree_verification

demo-defi: ## Run DeFi invariant verification.
	@./scripts/run_scenario.sh defi_invariant

demo-arklib: ## Run the ArkLib-style audit.
	@./scripts/run_scenario.sh arklib_style_audit

demo-charter: ## Run the Charter Gate scenario.
	@./scripts/run_scenario.sh charter_gate_demo

.PHONY: demo-charter-regression
demo-charter-regression: ## Run Charter, negative-control, observation, and evidence-regression checks.
	@status=0; \
	for scenario in charter_gate_demo negative_controls_demo test_observation_demo; do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	python3 scripts/check_evidence_regressions.py reports/charter_gate_demo/latest/result.json \
		--out-dir reports/charter_regressions || status=1; \
	exit "$$status"

demo-negative-controls: ## Run the negative-controls scenario.
	@./scripts/run_scenario.sh negative_controls_demo

demo-test-observation: ## Run the test-observation scenario.
	@./scripts/run_scenario.sh test_observation_demo

demo-self-correction: ## Run the self-correction scenario.
	@./scripts/run_scenario.sh self_correction_demo

demo-human-review: ## Run the human-review demo scenario.
	@./scripts/run_scenario.sh human_review_demo

.PHONY: demo-record-execution
demo-record-execution: ## Run the optional single-process record-execution experiment.
	@./scripts/run_scenario.sh record_execution_demo

demo-go-summaries: ## Declared go-summaries route loop (fixture mode unless CI_FIXTURE_MODE=0).
	@mode="$${CI_FIXTURE_MODE:-1}"; \
	if [ "$$mode" = "1" ]; then \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh go_summaries \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	else \
		./scripts/run_scenario.sh go_summaries \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	fi

demo-ts-summaries: ## Declared ts-summaries route loop (in-process analyzer, always deterministic).
	@./scripts/run_scenario.sh ts_summaries \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-rust-summaries: ## Declared rust-summaries route loop (in-process analyzer, always deterministic).
	@./scripts/run_scenario.sh rust_summaries \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-sol-summaries: ## Declared sol-summaries route loop (in-process analyzer, always deterministic).
	@./scripts/run_scenario.sh sol_summaries \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-audit-summaries: ## Directory audit with declared summaries (helper step fixture-mode unless CI_FIXTURE_MODE=0).
	@mode="$${CI_FIXTURE_MODE:-1}"; \
	if [ "$$mode" = "1" ]; then \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh audit_summaries \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	else \
		./scripts/run_scenario.sh audit_summaries \
			--mumei-agent-repo "$(MUMEI_AGENT_REPO)"; \
	fi

demo-translation-validation: ## Build --emit binary translation-validation advisory (real mumei binary).
	@./scripts/run_scenario.sh translation_validation \
		--mumei-repo "$(MUMEI_REPO)"

demo-verify-recheck: ## Declared evidence recheck route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh verify_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-verify-attempt: ## Declared verify attempt route with live evidence check (real mumei + mumei-agent).
	@./scripts/run_scenario.sh verify_attempt \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-recheck: ## Declared native consumer recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-identity: ## Declared evidence file-identity route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_identity \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-check-accept: ## Declared evidence-check acceptance route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_check_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-compare: ## Declared evidence record-vs-record comparison route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_compare \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-attempt: ## Declared native bundle production route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_attempt \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-check: ## Declared native bundle check route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_check \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-artifact-recheck: ## Declared native artifact recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_artifact_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-refined-attempt: ## Declared refined-scalar (v2) native bundle production route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_refined_attempt \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-refined-widened-attempt: ## Declared widened refined-scalar (v3) native bundle production route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_refined_widened_attempt \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-composite-attempt: ## Declared composite struct-member (v4) native bundle production route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_composite_attempt \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-accept: ## Declared native artifact acceptance route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-evidence-recheck: ## Declared native evidence replay route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_evidence_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-evidence-accept: ## Declared native evidence acceptance route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_evidence_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-source-recheck: ## Declared native source recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_source_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-exit-status-recheck: ## Declared native exit-status recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_exit_status_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-exit-status-accept: ## Declared native exit-status acceptance route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_exit_status_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-stdout-recheck: ## Declared native stdout recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_stdout_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-stdout-accept: ## Declared native stdout acceptance route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_stdout_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-stderr-recheck: ## Declared native stderr recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_stderr_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-stderr-accept: ## Declared native stderr acceptance route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_stderr_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-observations-accept: ## Declared native observations acceptance route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_observations_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-observations-recheck: ## Declared native observations recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_observations_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-object-recheck: ## Declared native object recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_object_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-machine-tv-recheck: ## Declared native leaf machine-code TV recheck route (real mumei + mumei-agent, native toolchain).
	@./scripts/run_scenario.sh native_machine_tv_recheck \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-check-schedule: ## Declared Evidence attempt-schedule representation check (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_check_schedule \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-check-attempt-acceptance: ## Declared attempt-acceptance representation check (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_check_attempt_acceptance \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-native-observations-recovery: ## C13 native observations recovery-composition regression (real mumei + mumei-agent).
	@./scripts/run_scenario.sh native_observations_recovery \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-verify-accept: ## Declared source-evidence acceptance route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh verify_accept \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-check-list: ## Declared evidence list-envelope check route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_check_list \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-check-consistency: ## Declared evidence cross-record consistency route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_check_consistency \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-all: demo ## Compatibility alias for the default demo target.

demo-ci: ## Run default scenarios in fixture mode and regenerate reports.
	@status=0; \
	for scenario in $(SCENARIOS); do \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	$(MAKE) report || status=1; \
	exit "$$status"

demo-scale: ## Run all large-scale scenarios.
	@status=0; \
	for scenario in $(SCALE_SCENARIOS); do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	exit "$$status"

demo-medical-scale: ## Run medical-device large-scale verification.
	@./scripts/run_scenario.sh medical_device_scale

demo-settlement-scale: ## Run settlement large-scale verification.
	@./scripts/run_scenario.sh rtgs_settlement_scale

demo-regtech-scale: ## Run RegTech large-scale verification.
	@./scripts/run_scenario.sh regtech_compliance_scale

demo-defi-scale: ## Run DeFi large-scale verification.
	@./scripts/run_scenario.sh defi_invariant_scale

demo-ownership-scale: ## Run ownership-transfer large-scale verification.
	@./scripts/run_scenario.sh ownership_transfer_scale

report: ## Regenerate the summary and highlights from scenario reports.
	@python3 scripts/generate_report.py --summary --highlights --require-all

.PHONY: test-record-execution
test-record-execution: ## Run focused tests for record-execution checks.
	@python3 -m pytest tests/test_record_execution.py -q

setup: ## Set up sibling repositories and build/install their tools.
	@./scripts/setup_repos.sh

demo-evidence-check: ## Declared evidence representation check route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_check \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-summaries-plan: ## Declared summary-route planning (probe boundary + resume).
	@./scripts/run_scenario.sh summaries_plan \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-summaries-attempt: ## Declared summary attempt routes (ts/rust/sol + timeout refusal).
	@./scripts/run_scenario.sh summaries_attempt \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-evidence-producer: ## Declared evidence producer-identity route (real mumei + mumei-agent).
	@./scripts/run_scenario.sh evidence_producer \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-producer-signature-recovery: ## Producer-authenticity lane: keygen, sign, pinned verify, recovery (real mumei + mumei-agent).
	@./scripts/run_scenario.sh producer_signature_recovery \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-agent-signature-sign: ## Agent-side producer lane: keygen, signature-sign, pinned verify, recovery (real mumei + mumei-agent).
	@./scripts/run_scenario.sh agent_signature_sign \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-claimbook-acceptance-gate: ## Promotable acceptance gate: accepted triple promotes, tampered fails closed (real mumei).
	@./scripts/run_scenario.sh claimbook_acceptance_gate \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-schedule-export-gate: ## Scheduled promotable export: verify-schedule exports the gate triple (real mumei core + claims gate).
	@./scripts/run_scenario.sh schedule_export_gate \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"
