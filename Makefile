.PHONY: test test-self test-proof test-all score lint install install-dev clean help

SKILL_DIR := skills/skillforge

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

test: ## Run integration tests (99+ tests)
	cd $(SKILL_DIR) && bash scripts/test-integration.sh --no-runtime-auto

test-self: ## Run self-tests (12 tests)
	cd $(SKILL_DIR) && bash scripts/test-self.sh

test-proof: ## Run proof tests (6 tests)
	cd $(SKILL_DIR) && bash tests/proof/test-proof.sh

test-all: test test-self test-proof ## Run all test suites

score: ## Score SkillForge's own SKILL.md
	cd $(SKILL_DIR) && python3 scripts/score-skill.py SKILL.md

score-json: ## Score with JSON output
	cd $(SKILL_DIR) && python3 scripts/score-skill.py SKILL.md --json

lint: ## Run ruff linter on scripts
	ruff check $(SKILL_DIR)/scripts/ || echo "Install ruff: pip install ruff"

install: ## Install SkillForge (copy mode)
	bash install.sh

install-dev: ## Install SkillForge (symlink mode for development)
	bash install.sh --link

clean: ## Remove __pycache__ and .pyc files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
