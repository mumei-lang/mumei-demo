SCENARIOS := ownership_transfer rtgs_settlement regtech_compliance nl_to_verified smart_contract_audit medical_device aviation_control

.PHONY: demo demo-ownership demo-settlement demo-regtech demo-nl demo-smart-contract demo-medical demo-aviation demo-all demo-ci report setup

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
	@./scripts/run_scenario.sh nl_to_verified

demo-smart-contract:
	@./scripts/run_scenario.sh smart_contract_audit

demo-medical:
	@./scripts/run_scenario.sh medical_device

demo-aviation:
	@./scripts/run_scenario.sh aviation_control

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
