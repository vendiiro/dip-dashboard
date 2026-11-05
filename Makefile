# Thin wrapper: every target calls tasks.py, which holds the logic. On Windows (no make): python tasks.py <command>.
PY ?= python

.PHONY: install unit browser test demo shots check hooks
install:
	$(PY) tasks.py install

unit:
	$(PY) tasks.py test

browser:
	$(PY) tasks.py test-browser

test:
	$(PY) tasks.py all

demo:
	$(PY) tasks.py demo

shots:
	$(PY) tasks.py shots

check:
	$(PY) tasks.py check

hooks:
	$(PY) tasks.py hooks
