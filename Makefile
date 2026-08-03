# 天链V3 边缘网关 — 开发快捷命令
.PHONY: venv install run test lint check clean deploy

VENV=.venv
PYTHON=$(VENV)/bin/python

venv:
	python3 -m venv $(VENV)

install: venv
	$(VENV)/bin/pip install -r requirements.txt

run:
	$(PYTHON) main.py

test:
	$(VENV)/bin/pytest -x -q --timeout=30

lint:
	$(VENV)/bin/ruff check .

check: lint test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete; \
	rm -f .coverage; \
	rm -rf .pytest_cache

deploy:
	bash deploy.sh
