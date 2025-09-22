.PHONY: venv fmt lint test run dryrun

venv:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -e .[dev]

fmt:
	ruff check --fix pm_arb_bot tests

lint:
	ruff check pm_arb_bot tests
	mypy pm_arb_bot

test:
	pytest

run:
	python -m pm_arb_bot.cli run --config config.example.yaml --dry-run

dryrun:
	python -m pm_arb_bot.cli run --config config.example.yaml --dry-run
