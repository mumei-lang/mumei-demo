.PHONY: demo demo-settlement demo-regtech demo-nl demo-smart-contract demo-aviation demo-all demo-ci report setup

demo:
	@./scripts/run_scenario.sh ownership_transfer

demo-settlement:
	@./scripts/run_scenario.sh rtgs_settlement

demo-regtech:
	@./scripts/run_scenario.sh regtech_compliance

demo-nl:
	@./scripts/run_scenario.sh nl_to_verified

demo-smart-contract:
	@./scripts/run_scenario.sh smart_contract_audit

demo-aviation:
	@./scripts/run_scenario.sh aviation_control

demo-all:
	@./scripts/run_scenario.sh ownership_transfer
	@./scripts/run_scenario.sh rtgs_settlement
	@./scripts/run_scenario.sh regtech_compliance
	@./scripts/run_scenario.sh nl_to_verified
	@./scripts/run_scenario.sh smart_contract_audit
	@./scripts/run_scenario.sh aviation_control

demo-ci:
	@status=0; \
	for scenario in ownership_transfer rtgs_settlement regtech_compliance nl_to_verified smart_contract_audit aviation_control; do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	$(MAKE) report || status=1; \
	exit "$$status"

report:
	@python3 scripts/generate_report.py --summary --highlights --require-all

setup:
	@./scripts/setup_repos.sh
