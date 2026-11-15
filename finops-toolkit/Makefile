.PHONY: lint test run

lint:
	python -m ruff check src tests

test:
	python -m unittest discover -s tests -v

run:
	finops report --fixtures tests/fixtures
