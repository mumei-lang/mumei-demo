.PHONY: demo demo-settlement demo-regtech demo-nl demo-all demo-ci setup

demo:
	@./scripts/run_scenario.sh ownership_transfer

demo-settlement:
	@./scripts/run_scenario.sh rtgs_settlement

demo-regtech:
	@./scripts/run_scenario.sh regtech_compliance

demo-nl:
	@./scripts/run_scenario.sh nl_to_verified

demo-all:
	@./scripts/run_scenario.sh ownership_transfer
	@./scripts/run_scenario.sh rtgs_settlement
	@./scripts/run_scenario.sh regtech_compliance
	@./scripts/run_scenario.sh nl_to_verified

demo-ci:
	@status=0; \
	for scenario in ownership_transfer rtgs_settlement regtech_compliance nl_to_verified; do \
		./scripts/run_scenario.sh "$$scenario" || status=1; \
	done; \
	python3 scripts/generate_report.py --summary --require-all || status=1; \
	exit "$$status"

setup:
	@./scripts/setup_repos.sh
