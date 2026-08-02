PYTHON ?= python3
VENV_PYTHON ?= .venv/bin/python
VENV_SMC_DATA ?= .venv/bin/smc-data

.PHONY: setup ready verify-prepared test lint plan-golden plan-history package

setup:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install -e .
	$(VENV_SMC_DATA) ready --verify

ready:
	PYTHONPATH=src $(PYTHON) -m smc_ict_data.cli ready

verify-prepared:
	PYTHONPATH=src $(PYTHON) -m smc_ict_data.cli ready --verify

test:
	PYTHONPATH=src $(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests

plan-golden:
	PYTHONPATH=src $(PYTHON) -m smc_ict_data.cli plan --start 2024-01-01 --end 2024-01-31 --as-of 2024-02-12 --out data/manifests/golden_2024_01.csv

plan-history:
	PYTHONPATH=src $(PYTHON) -m smc_ict_data.cli plan --out data/manifests/full_history_candidates.csv

package:
	git archive --format=zip --output=SMC_ICT_3_LIVE-source.zip HEAD
