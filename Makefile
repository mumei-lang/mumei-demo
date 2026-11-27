SCENARIOS := ownership_transfer rtgs_settlement regtech_compliance nl_to_verified no_mm_audit spec_code_verification_suite mumei_develop_audit smart_contract_audit blockchain_audit medical_device aviation_control merkle_tree_verification defi_invariant arklib_style_audit charter_gate_demo negative_controls_demo test_observation_demo self_correction_demo
# Large-scale (Priority 16) targets. Kept out of SCENARIOS on purpose: they are
# separate targets so the deterministic fixture-mode CI run stays unchanged.
SCALE_SCENARIOS := medical_device_scale rtgs_settlement_scale regtech_compliance_scale defi_invariant_scale ownership_transfer_scale
OPTIONAL_SCENARIOS := record_execution_demo go_summaries ts_summaries rust_summaries sol_summaries rust_bindings sol_bindings ts_bindings audit_summaries translation_validation ci_evidence_pack verify_recheck verify_attempt native_recheck evidence_identity evidence_check_accept evidence_compare native_attempt native_check native_artifact_recheck native_refined_attempt native_refined_widened_attempt verify_accept evidence_acceptance_eval evidence_fold_eval check_spec_health evidence_accept_list evidence_check_adapter evidence_check_attempt_acceptance evidence_check_list evidence_check_consistency native_accept native_evidence_recheck native_evidence_accept native_source_recheck native_exit_status_recheck native_exit_status_accept native_stdout_recheck native_stdout_accept native_stderr_recheck native_stderr_accept native_observations_accept native_observations_recheck native_object_accept native_object_recheck native_machine_tv_recheck native_machine_tv_branch_call_recheck native_machine_tv_bounded_loop_recheck native_machine_tv_f64_recheck native_machine_tv_composite_recheck evidence_check_schedule native_observations_recovery native_composite_attempt evidence_check summaries_plan summaries_attempt summaries_reuse_attempt verify_plan evidence_producer producer_signature_recovery agent_signature_sign claimbook_acceptance_gate schedule_export_gate
# Optional scenarios with custom fixture, repository-argument, or reporting behavior.
OPTIONAL_CUSTOM_SCENARIOS := record_execution_demo go_summaries ts_summaries rust_summaries sol_summaries rust_bindings sol_bindings ts_bindings audit_summaries translation_validation
# Uniform optional scenarios use the same public target shape:
# demo-<scenario-with-hyphens> runs the scenario with both sibling repository arguments.
DUAL_REPO_SCENARIOS := $(filter-out $(OPTIONAL_CUSTOM_SCENARIOS),$(OPTIONAL_SCENARIOS))
DUAL_REPO_SCENARIO_TARGETS := $(foreach scenario,$(DUAL_REPO_SCENARIOS),demo-$(subst _,-,$(scenario)))
NO_MM_AUDIT_LANGUAGES := python rust typescript go
MUMEI_REPO ?= ../mumei
MUMEI_AGENT_REPO ?= ../mumei-agent

.PHONY: demo demo-ownership demo-settlement demo-regtech demo-nl demo-no-mm demo-no-mm-multilang demo-spec-code demo-mumei-develop-audit demo-smart-contract demo-blockchain demo-medical demo-aviation demo-merkle demo-defi demo-arklib demo-charter demo-negative-controls demo-test-observation demo-self-correction demo-human-review demo-all demo-ci report setup help \
	demo-scale demo-medical-scale demo-settlement-scale demo-regtech-scale demo-defi-scale demo-ownership-scale \
	demo-go-summaries demo-ts-summaries demo-rust-summaries demo-sol-summaries demo-rust-bindings demo-sol-bindings demo-ts-bindings demo-audit-summaries \
	demo-translation-validation

demo: ## Run the default scenario set and regenerate summary reports.
	@status=0; \
	for scenario in $(SCENARIOS); do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	$(MAKE) report || status=1; \
	exit "$$status"

help: ## List Make targets and their descriptions.
	@awk 'BEGIN { FS = ":.*##" } /^[[:alnum:]_.-]+:.*##/ { printf "  %-30s %s\n", $$1, $$2 }' $(MAKEFILE_LIST); \
	for target in $(DUAL_REPO_SCENARIO_TARGETS); do \
		scenario="$$(printf '%s' "$${target#demo-}" | tr '-' '_')"; \
		printf '  %-30s %s\n' "$$target" "Run the $$scenario scenario (real mumei + mumei-agent)."; \
	done

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

demo-rust-bindings: ## Rust lexical binding metadata route (in-process; no toolchain).
	@./scripts/run_scenario.sh rust_bindings \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-sol-bindings: ## Solidity lexical binding metadata route (in-process; no toolchain).
	@./scripts/run_scenario.sh sol_bindings \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-ts-bindings: ## TypeScript lexical binding metadata route (in-process; no toolchain).
	@./scripts/run_scenario.sh ts_bindings \
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

.PHONY: $(DUAL_REPO_SCENARIO_TARGETS)
$(DUAL_REPO_SCENARIO_TARGETS): demo-%:
	@./scripts/run_scenario.sh $(subst -,_,$*) \
		--mumei-repo "$(MUMEI_REPO)" \
		--mumei-agent-repo "$(MUMEI_AGENT_REPO)"

demo-all: demo ## Compatibility alias for the default demo target.

DEMO_CI_JOBS ?= 4

demo-ci: ## Run default scenarios in fixture mode and regenerate reports.
	@status=0; \
	jobs=$(DEMO_CI_JOBS); \
	if command -v lake >/dev/null 2>&1; then \
		jobs=1; \
		echo "demo-ci: lake detected — running serially to avoid racing the shared Lean checkout"; \
	fi; \
	printf '%s\n' $(SCENARIOS) \
		| xargs -P$$jobs -n1 sh -c 'CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh "$$0"' \
		|| status=1; \
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
