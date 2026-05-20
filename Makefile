.PHONY: help install dev-install test test-verbose lint clean docker-build docker-run smoke

PYTHON ?= python3

help:
	@echo "Targets:"
	@echo "  install        Install the package"
	@echo "  dev-install    Install with dev extras (editable)"
	@echo "  test           Run the test suite"
	@echo "  test-verbose   Run tests with -v"
	@echo "  smoke          End-to-end CLI smoke test against a temp db"
	@echo "  clean          Remove build / cache artifacts"
	@echo "  docker-build   Build the Docker image"
	@echo "  docker-run     Run the CLI inside Docker (pass ARGS=...)"

install:
	$(PYTHON) -m pip install .

dev-install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -t .

test-verbose:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -t . -v

smoke:
	@DB=$$(mktemp -u --suffix=.db); \
	export FINANCE_DATABASE_PATH=$$DB PYTHONPATH=src; \
	$(PYTHON) -m finance_tracker account add Smoke --type checking --opening-balance 100 && \
	$(PYTHON) -m finance_tracker category add Food --kind expense && \
	$(PYTHON) -m finance_tracker transaction add 12.34 --account Smoke --category Food --description Coffee && \
	$(PYTHON) -m finance_tracker report balances && \
	rm -f $$DB

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

docker-build:
	docker build -t finance-tracker:local .

docker-run:
	docker run --rm -v finance-data:/data finance-tracker:local $(ARGS)
