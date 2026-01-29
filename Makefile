BASE_DIR		:= $(shell git rev-parse --show-toplevel 2>/dev/null || pwd)
PROG_NAME		:= $(shell basename $(BASE_DIR))
PYPROJECT		:= $(shell find . -name 'pyproject.toml')
SHELL			:= /bin/bash
UV_LOCK			:= uv.lock
UV				?= uv
VENV			:= .venv
MARKER			:= $(VENV)/.installed

################################################################
#%
#% Usage:
#%   make <command>
#%
#% Getting Started:
#%   make setup
#%
#% Run the tests locally:
#%   make test
#%
#% Available Commands:
help: ## Help is on the way
	@echo " Tools for building, running, and testing $(PROG_NAME)"
	@grep '^#%' $(MAKEFILE_LIST) | sed -e 's/#%//'
	@grep '^[a-zA-Z]' $(MAKEFILE_LIST) | awk -F ':.*?## ' 'NF==2 {printf "   %-20s%s\n", $$1, $$2}' | sort

# export env vars in order to be used in commands
export PYTHONPATH ?= ./

# uv creates the venv automatically, but this tracks if sync has been run
$(MARKER): $(PYPROJECT) $(UV_LOCK)
	$(UV) sync --all-extras
	touch $(MARKER)

.PHONY: install
setup: $(MARKER) ## Install dependencies for the project

.PHONY: update
update: ## Update and lock dependencies
	$(UV) lock
	$(UV) sync
	touch $(MARKER)

.PHONY: clean
clean: ## Remove virtual environment
	rm -rf $(VENV)

.PHONY: deps
deps: $(MARKER) ## Run any dependencies for local dev and test
	@echo "Starting deps..."

.PHONY: dev
dev: deps ## Run the application in dev mode
	$(UV) run cuneus dev

.PHONY: prod
prod: deps ## Run the application in prod mode
	$(UV) run cuneus prod

.PHONY: test
test: deps ## Run pytests
	$(UV) run pytest

.PHONY: test-failed
test-failed: deps ## Re-Run pytest on tests that failed
	$(UV) run pytest --lf


