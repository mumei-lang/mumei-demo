SCENARIOS := ownership_transfer rtgs_settlement regtech_compliance nl_to_verified no_mm_audit spec_code_verification_suite mumei_develop_audit smart_contract_audit blockchain_audit medical_device aviation_control merkle_tree_verification defi_invariant arklib_style_audit self_correction_demo
# Large-scale (Priority 16) targets. Kept out of SCENARIOS on purpose: they are
# separate targets so the deterministic fixture-mode CI run stays unchanged.
SCALE_SCENARIOS := medical_device_scale rtgs_settlement_scale regtech_compliance_scale defi_invariant_scale ownership_transfer_scale
NO_MM_AUDIT_LANGUAGES := python rust typescript go
MUMEI_REPO ?= ../mumei
MUMEI_AGENT_REPO ?= ../mumei-agent

.PHONY: demo demo-ownership demo-settlement demo-regtech demo-nl demo-no-mm demo-no-mm-multilang demo-spec-code demo-mumei-develop-audit demo-smart-contract demo-blockchain demo-medical demo-aviation demo-merkle demo-defi demo-arklib demo-self-correction demo-human-review demo-all demo-ci report setup \
	demo-scale demo-medical-scale demo-settlement-scale demo-regtech-scale demo-defi-scale demo-ownership-scale

demo:
	@status=0; \
	for scenario in $(SCENARIOS); do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	$(MAKE) report || status=1; \
	exit "$$status"


demo-ownership:
	@./scripts/run_scenario.sh ownership_transfer

demo-settlement:
	@./scripts/run_scenario.sh rtgs_settlement

demo-regtech:
	@./scripts/run_scenario.sh regtech_compliance

demo-nl:
	@mode="$${CI_FIXTURE_MODE:-1}"; \
	if [ "$$mode" = "1" ]; then \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh nl_to_verified; \
	else \
		./scripts/run_scenario.sh nl_to_verified; \
	fi
	@python3 scripts/generate_report.py reports/nl_to_verified/latest/result.json --format markdown --report-output reports/nl_to_verified/latest/report.md
	@python3 dashboard/cli_report.py reports/nl_to_verified/latest/result.json

demo-no-mm:
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

demo-no-mm-multilang: demo-no-mm

demo-spec-code:
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

demo-mumei-develop-audit:
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

demo-smart-contract:
	@./scripts/run_scenario.sh smart_contract_audit

demo-blockchain:
	@./scripts/run_blockchain_audit.sh

demo-medical:
	@./scripts/run_scenario.sh medical_device

demo-aviation:
	@./scripts/run_scenario.sh aviation_control

demo-merkle:
	@./scripts/run_scenario.sh merkle_tree_verification

demo-defi:
	@./scripts/run_scenario.sh defi_invariant

demo-arklib:
	@./scripts/run_scenario.sh arklib_style_audit

demo-self-correction:
	@./scripts/run_scenario.sh self_correction_demo

demo-human-review:
	@./scripts/run_scenario.sh human_review_demo

demo-all: demo

demo-ci:
	@status=0; \
	for scenario in $(SCENARIOS); do \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	$(MAKE) report || status=1; \
	exit "$$status"

demo-scale:
	@status=0; \
	for scenario in $(SCALE_SCENARIOS); do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	exit "$$status"

demo-medical-scale:
	@./scripts/run_scenario.sh medical_device_scale

demo-settlement-scale:
	@./scripts/run_scenario.sh rtgs_settlement_scale

demo-regtech-scale:
	@./scripts/run_scenario.sh regtech_compliance_scale

demo-defi-scale:
	@./scripts/run_scenario.sh defi_invariant_scale

demo-ownership-scale:
	@./scripts/run_scenario.sh ownership_transfer_scale

report:
	@python3 scripts/generate_report.py --summary --highlights --require-all

setup:
	@./scripts/setup_repos.sh
