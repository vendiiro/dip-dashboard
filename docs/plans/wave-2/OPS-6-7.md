# OPS-6 + OPS-7 · one task runner and two pre-commit guards

**Owner:** test-engineer · **Reviewer:** wording-guard (scan word list and scope) · **Skills:** `engineering:testing-strategy` · **Size:** S-M (about 200 lines)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
Add `tasks.py` (stdlib only, same commands on Linux and Iiro's Windows PC) with `demo`, `test`, `test-browser`, `shots`, `check`.
Add pre-commit guards: a wording scan and a block on staged `data/`, `output/`, `.env`. Files: `tasks.py`, `.pre-commit-config.yaml`,
`scripts/check_wording.py` (all already in ownership.csv lines 126-128, so no ownership change is needed).

## How tasks.py relates to the Makefile and CI
- **Keep both; the Makefile becomes a thin wrapper.** Each target turns into `$(PY) tasks.py <name>`, so the logic lives in one place.
  Windows has no make, so `python tasks.py x` is the documented route; `make x` stays for Linux habits.
- **CI keeps its explicit `pytest` lines** (they set `DIP_REQUIRE_BROWSER` per job and are the source of truth for the matrix).
  CI adds one step, `python tasks.py check`, to the unit job so the guards also run when a hook was skipped (`--no-verify`).
- Commands: `demo` = `python -m dipdash --demo --out output/demo.html` (sets `PYTHONPATH=src`, `PYTHONIOENCODING=utf-8`);
  `test` = the Makefile `unit` line; `test-browser` = the `browser` line; `shots` = demo then `scripts/screenshots.py`;
  `check` = wording scan over all files + forbidden-path scan over tracked files + `pytest -q --ignore=tests/test_browser.py`.
  Use `sys.executable`, `subprocess.run` with a list (no shell), and `pathlib`, so no quoting differences between the two OSes.

## How the wording scan relates to the existing test
- `tests/test_alerts.py::test_no_banned_words_anywhere` (and the digest test) check **generated text**: alert and digest output, plus
  three source files. They stay; they catch wording that only appears at run time.
- `scripts/check_wording.py` checks **source files as written**, before commit: `src/`, `config/`, `scripts/*.ps1|bat`, `README.md`,
  `START_HERE.md`. It does not replace the tests; it catches a planted phrase in files no test reads (template, README).
- **Scope:** phrases only (`buy now`, `sell`, `price target`, `will recover`, `guarantee`), not the wider alert list (`entry`, `should`,
  `target`), because those words are ordinary in code and in the CLAUDE.md rules. Skipped: `tests/`, `docs/`, `.claude/`, `CLAUDE.md`
  (they quote the words as examples; test_digest.py has one on purpose).
- The script writes the patterns split (`"bu" + "y now"`) like test_alerts.py, so it does not match itself. Exit 1 prints file:line.

## Pre-commit guards
- `.pre-commit-config.yaml` with two `repo: local`, `language: system` hooks: `check_wording.py` (passes staged filenames) and a path
  guard, also in `check_wording.py --paths`, that rejects staged `data/`, `output/`, `.env`, `.env.*` but allows `.env.example`.
- `.gitignore` already lists `.env`, `data/`, `output/`; the hook covers `git add -f`. `snapshots/` stays allowed.
- Install is one line: `python tasks.py hooks` runs `pre-commit install`. `pre-commit` goes in `requirements-dev.txt`, pinned.

## Verification
`python tasks.py check` green on a clean tree; a planted "buy now" in `src/dipdash/digest.py` and a force-added `output/x.html` are
rejected (checked by hand once, then as `tests/test_guards.py` calling the script on tmp_path files). `pytest -q` full run.

## Open questions
1. **Hook runner.** (a) the `pre-commit` package, (b) a plain `.git/hooks/pre-commit` that calls `tasks.py guard`, (c) both: package config,
   with the guard logic in the script so CI can call it. **Recommend (c)**; the backlog names `.pre-commit-config.yaml`, and CI needs no package.
2. **Scan scope.** (a) phrases only in user-visible sources, (b) the full alert word list everywhere, (c) phrases only, plus the full list on
   generated demo output. **Recommend (a)**; (b) gives false hits on `target`, `entry` in code. Generated text is already tested.
3. **Make's future.** (a) keep as wrapper, (b) delete, (c) keep untouched. **Recommend (a)**: one source of logic, no break for Linux users.

## Risks
`pre-commit` is a new dependency (reason: the hooks run the same on Windows without shell scripts). The repo may not be a git checkout
in the build sandbox, so hook install is tested only on Iiro's PC; the script's checks are tested without git, on file lists.

## Handoff (to be filled by the builder)
1. Done  2. Checked  3. Not checked  4. Requests to other owners (docs-steward: add `python tasks.py` to TESTING.md and README)  5. Decision-log line
