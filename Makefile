SCENARIOS := ownership_transfer rtgs_settlement regtech_compliance nl_to_verified no_mm_audit spec_code_verification_suite mumei_develop_audit smart_contract_audit blockchain_audit medical_device aviation_control merkle_tree_verification defi_invariant arklib_style_audit charter_gate_demo negative_controls_demo test_observation_demo self_correction_demo
# Large-scale (Priority 16) targets. Kept out of SCENARIOS on purpose: they are
# separate targets so the deterministic fixture-mode CI run stays unchanged.
SCALE_SCENARIOS := medical_device_scale rtgs_settlement_scale regtech_compliance_scale defi_invariant_scale ownership_transfer_scale
OPTIONAL_SCENARIOS := record_execution_demo
NO_MM_AUDIT_LANGUAGES := python rust typescript go
MUMEI_REPO ?= ../mumei
MUMEI_AGENT_REPO ?= ../mumei-agent

.PHONY: demo demo-ownership demo-settlement demo-regtech demo-nl demo-no-mm demo-no-mm-multilang demo-spec-code demo-mumei-develop-audit demo-smart-contract demo-blockchain demo-medical demo-aviation demo-merkle demo-defi demo-arklib demo-charter demo-negative-controls demo-test-observation demo-self-correction demo-human-review demo-all demo-ci report setup help \
	demo-scale demo-medical-scale demo-settlement-scale demo-regtech-scale demo-defi-scale demo-ownership-scale

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
