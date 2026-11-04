# RES-4 · one pre-registration and trial registry; all three runners use it

**Owner:** backtest-analyst · **Reviewer:** stats-reviewer · **Skills:** `backtest-hygiene`, `data:statistical-analysis` · **Size:** M (about 6 h, mostly tests)
**Planned 2026-11-04 (plan only; nothing changed yet).** Run after OPS-2 + RES-7: all three touch `backtest_run.py` and `backtest_report.py`.

## Understanding
Today each runner has its own pre-registration habit. `backtest_run.freeze_spec` writes spec.json and an archive by hash, and appends cells to
`trials.csv`. `run_feature_experiment.py` writes `spec_features.json` and `trials_features.csv` with a different layout and a second copy of the
hash function (`feature_experiment.spec_hash`). `run_forecast_calibration.py` has no spec file and no trial log; its criterion sits in a docstring and
module constants. "Register before computing" is a comment, not something a test can fail. Nothing records which out-of-sample period was already viewed.

## Design (`src/dipdash/registry.py`, stdlib + pandas)
1. `spec_hash(spec, excluded_keys)`: the one canonical hash (sha256 of sorted-key JSON, first 16 hex). Excluded keys stay per kind:
   backtest `{revisions_after_first_look, sample_notes}`, features `{notes}`, forecast `{notes}`. A golden test pins today's hashes so none change.
2. `register(kind, spec, out_dir, root) -> Registration`. Checks required fields (hypothesis or criterion text, pass/fail rule, split cutoff, horizon(s),
   planned cell count, data sha256). Writes `spec_<hash>.json` once (never overwritten) and appends a row to `registry.csv`
   (`registered_at, kind, family_id, spec_hash, oos_start, oos_end, raw_sha256, planned_cells`). Returns a frozen token.
3. `record_trials(reg, rows)`: the only writer of the trial log; refuses without a token, or if the rows' spec hash differs from the token's.
   One long schema: `run_at, kind, family_id, spec_hash, cell, stat, group, period, horizon, n, estimate, lo, hi, p_raw, p_holm, primary`.
   `cell` is variant, feature or method. A layout mismatch still sets the file aside, as `append_trials` does now.
4. Period ledger, derived from `registry.csv`: `earlier_specs(kind)` and `periods_viewed(oos_start, oos_end)`. At registration, any earlier
   registration that used an overlapping out-of-sample window is written into the new spec's `notes` (not hashed) and printed in the report.
5. Runners: `run_backtest` registers right after `freeze_spec` and before `build_days`; `run_feature_experiment.py` replaces its `write_trials`;
   `run_forecast_calibration.py` gets a frozen spec from its constants (H, STEP, MIN_OBS, OOS_FRACTION, METHODS, TARGET, tolerances, two attempts,
   verdict rule) and registers before `build_origins`. Forecast trial cells are coverage and pinball rows by group x method x attempt; the primary cells are the two verdict rows.

## Interaction with `backtest_notes.py` and `earlier_specs_line`
- Notes stay in `backtest_notes.py`, keyed by spec hash, backtest only. The registry never reads them. Because notes keys are excluded from the hash,
  editing a note changes nothing in the registry (the existing test stays and a registry twin is added).
- Order inside `run_backtest`: `freeze_spec` (hash) -> `register` -> attach `revisions_for(hash)` to the in-memory spec for the report. The archived
  `spec_<hash>.json` keeps the notes as they were at first registration; later note edits show only in the report.
- `earlier_specs_line(hist, shash)` keeps its signature and text. Its input changes from "hashes seen in `trials.csv`" to
  `registry.earlier_specs("backtest")`, so a run that registered and then crashed still counts as an earlier spec. It is scoped by kind, so a
  features or forecast registration is never described as an earlier backtest spec. `primary_history` (the numbers) still comes from the trial log.
- One-off backfill (`scripts/` helper in backtest-analyst's files): import hashes from the existing `trials.csv` and `trials_features.csv`
  (`90205cfc6da3a007`, `79288caaa97d33b1`, features spec) into `registry.csv`, marked `backfilled`. These were registered late and the ledger says so.
  This needs the real `output/backtests/` on Iiro's PC.

## Steps
1. `registry.py` + `tests/test_registry.py`: hash golden values, required fields, never-overwrite, token needed by `record_trials`, period overlap.
2. Refactor `backtest_run.py` (`append_trials` -> `record_trials`); `feature_experiment.spec_hash` delegates to the registry.
3. Both scripts as above; the forecast spec; `--out-root` honoured so tests use tmp dirs.
4. `backtest_report.py`: `earlier_specs_line` input from the ledger.
5. Guard test per runner: monkeypatch the compute entry points (`run_cells`, `evaluate_features`, `fc.all_ranges`) to assert that the spec file and a
   registry row already exist when they are called. Reorder the runner so compute comes first and the test must fail (a planted-fault check).

## Verification
`pytest tests/test_registry.py tests/test_backtest_run.py tests/test_feature_experiment.py tests/test_forecast.py -q`, then the full suite.
`--demo`-style synthetic universe through `run_backtest`; both scripts with `--limit` or a tiny synthetic raw file. A live re-run is not needed for the code.

## Stats-reviewer checks
Hashes unchanged for existing specs; the ledger counts a crashed run; trial counts per family match `planned_cells`; the forecast criterion in the spec
equals the docstring text; the period-reuse note is shown and not hidden behind notes; wording stays "historically, in this sample".

## Requests to other owners
orchestrator: add `src/dipdash/registry.py` and `tests/test_registry.py` to `docs/agents/ownership.csv` (backtest-analyst). test-engineer: none.

## Risks
Hash drift (guarded by the golden test). Old trial files differ in layout: left untouched, read only by the backfill. Registering before compute adds a
registry row for runs that fail later: intended.

## Open questions for Iiro
1. **Trial log layout.** (a) One long `trials_all.csv`, old files frozen and imported once (recommended); (b) keep three per-kind files with a shared
   header and the ledger; (c) SQLite. (a) gives one place to count trials; (c) is a new habit for little gain.
2. **Enforcing register-before-compute.** (a) Token required by `record_trials`, plus spy tests on the compute calls (recommended); (b) tests only;
   (c) require the spec file to be committed in git first (strongest, but the repo is not a git repo in the sandbox and slows every run).
3. **Out-of-sample window already viewed.** (a) Record and print a note in the spec and report, no block (recommended); (b) block unless `--ack-reuse` is passed;
   (c) record silently. (b) is stricter but trips on harmless re-runs of an unchanged spec.

**Decision-log line (if adopted):** 2026-11-04: all research runners pre-register through `registry.py` (one hash, one trial schema, a ledger of out-of-sample windows viewed); notes stay outside the hash.

## Handoff (planned)
1. Done: registry.py, tests/test_registry.py, backtest_run.py, both scripts, backtest_report.py (earlier_specs input), feature_experiment.py (hash delegate).
2. Checked: the pytest commands above (summary lines to be pasted). 3. Not checked: backfill against the real output folder; stats-reviewer pass.
4. Requests: ownership.csv entry (orchestrator). 5. Decision-log line: as above.
