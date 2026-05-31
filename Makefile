SCENARIOS := ownership_transfer rtgs_settlement regtech_compliance nl_to_verified smart_contract_audit medical_device aviation_control merkle_tree_verification defi_invariant arklib_style_audit

.PHONY: demo demo-ownership demo-settlement demo-regtech demo-nl demo-smart-contract demo-medical demo-aviation demo-merkle demo-defi demo-arklib demo-all demo-ci report setup

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

demo-smart-contract:
	@./scripts/run_scenario.sh smart_contract_audit

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

demo-all: demo

demo-ci:
	@status=0; \
	for scenario in $(SCENARIOS); do \
		CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	$(MAKE) report || status=1; \
	exit "$$status"

report:
	@python3 scripts/generate_report.py --summary --highlights --require-all

setup:
	@./scripts/setup_repos.sh
