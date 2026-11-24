PYTHON ?= python

.PHONY: lint test coverage custodian-validate run

lint:
	$(PYTHON) -m ruff check src tests

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

coverage:
	PYTHONPATH=src $(PYTHON) -m coverage run --source=finops -m unittest discover -s tests -v
	$(PYTHON) -m coverage report --fail-under=90 -m

custodian-validate:
	custodian validate custodian/policies/*.yml

run:
	PYTHONPATH=src $(PYTHON) -m finops.cli report --fixtures tests/fixtures
