# One command per check. On Windows without make: run the python lines directly.
PY ?= python

.PHONY: install test unit browser
install:
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m playwright install chromium

unit:
	$(PY) -m pytest -q --ignore=tests/test_browser.py

browser:
	$(PY) -m pytest -q -rs tests/test_browser.py

test:
	$(PY) -m pytest -q -rs
