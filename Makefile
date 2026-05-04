.PHONY: demo demo-settlement demo-regtech demo-nl demo-all setup

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
	@./scripts/run_scenario.sh nl_to_verified

setup:
	@./scripts/setup_repos.sh
