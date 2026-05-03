.PHONY: demo demo-settlement setup

demo:
	@./scripts/run_scenario.sh ownership_transfer

demo-settlement:
	@./scripts/run_scenario.sh rtgs_settlement

setup:
	@./scripts/setup_repos.sh
