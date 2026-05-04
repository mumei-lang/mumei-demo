.PHONY: demo demo-settlement demo-regtech demo-all setup

demo:
	@./scripts/run_scenario.sh ownership_transfer

demo-settlement:
	@./scripts/run_scenario.sh rtgs_settlement

demo-regtech:
	@./scripts/run_scenario.sh regtech_compliance

demo-all:
	@./scripts/run_scenario.sh ownership_transfer
	@./scripts/run_scenario.sh rtgs_settlement

setup:
	@./scripts/setup_repos.sh
