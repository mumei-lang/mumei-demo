.PHONY: demo setup

demo:
	@./scripts/run_scenario.sh ownership_transfer

setup:
	@./scripts/setup_repos.sh
