# DATA-1 · typed source contracts, a fake Yahoo, and the live branch tested offline

**Owners:** data-engineer (half 1, first), integrator (half 2, after half 1 merges) · **Reviewer:** none (no reader-facing text) · **Skills:** `openbb-data-pull`, `engineering:testing-strategy`, `engineering:architecture` · **Size:** M + M
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
Today the live branch of `cli.main` (cli.py:127-165) imports `yfinance` and calls `fetch_prices`, `fetch_fundamentals`, `fetch_indices`,
`fetch_fx_to_usd`, `load_earnings`, `fetch_news` and `_crosscheck` directly, so no test has ever run it; only `--demo` is covered.
Half 1 adds `src/dipdash/sources.py` (typing `Protocol`s plus one `Sources` bundle of the callables main needs) and `tests/fakes.py`
(a configurable fake Yahoo). Half 2 lets `main(argv, sources=None)` take that bundle and adds `tests/test_pipeline_live.py`. Existing
function seams (`pull_prices(primary, fallback)`, `fetch_indices(fetch_close=)`, `fetch_fx_to_usd(fetch_last=)`, `load_earnings(fetch=)`) are
reused, not rewritten. Default behaviour with `sources=None` must be byte-identical to today.

## Steps, half 1 (data-engineer: sources.py, tests/fakes.py; data.py, openbb_source.py, fx.py only if a signature needs it)
1. `sources.py` imports no network library. `Bars = tuple[pd.Series, pd.Series | None]` (close, volume), as already used everywhere.
   Protocols: `PriceSource.__call__(tickers) -> dict[str, Bars]`; `FundamentalsSource.__call__(tickers, cache_path) -> dict`; `FxSource.__call__(symbol) -> float | None`;
   `IndexSource.__call__(symbol) -> pd.Series | None`. Extra callables main needs (`fallback_bars`, `earnings`, `news`, `raw_closes`) get plain `Callable` aliases.
2. `Sources` frozen dataclass holding those fields; `live_sources()` returns the real ones with lazy imports (so importing sources.py stays cheap
   and offline-safe). `fetch_fundamentals` gets an optional `fetch_info=` seam (today it calls `yf.Ticker` inline, data.py:123); default unchanged.
3. `tests/fakes.py`: `FakeYahoo(prices={...}, *, fail=set(), lag={ticker: days}, nan_tail={ticker: n}, empty=set(), fund={...}, fx={...}, index={...})` built on
   `tests/synth.py` series (read only). It exposes `.sources()` returning a `Sources`, and records calls (`.calls`) so tests can assert nothing hit the network.
   Failure modes: raise, return empty, last bar N days old, trailing NaN, missing currency in fundamentals, FX pair absent, index absent.
4. `tests/test_sources.py`? Not in the ownership list, so put the half-1 checks in `tests/test_cache.py`-style existing owned files or ask the orchestrator for the pattern (see Requests).
   Checks: fakes drive `pull_prices` (primary fail -> fallback tagged "fallback"), `fetch_indices` (failed index omitted, `history` filled), `fetch_fx_to_usd` (absent pair omitted).

## Steps, half 2 (integrator: cli.py, tests/test_pipeline_live.py)
1. `main(argv=None, sources: Sources | None = None)`. In the live branch: `src = sources or live_sources()`; the `import yfinance` guard and warning filter run only when
   `sources is None`. Replace the direct calls with `src.*`; `_crosscheck` takes the bundle (skipped, with the existing message, when none is supplied).
2. `tests/test_pipeline_live.py` with `tmp_path` and `FakeYahoo` (no network; monkeypatch `yfinance` import to raise as a tripwire):
   - happy path: raw files in `data/raw/yfinance*`, `dashboard.html`, `digest.md`, `data_quality.csv`, exit 0.
   - primary fails for one ticker: raw file `openbb_fallback`, `price_source` warn in the log.
   - lagged and NaN-tail tickers: stale and bad-bar issues appear with severity and detail.
   - index missing: `index_missing` warn. FX missing: no crash, size check marked unknown.
   - exit code 2 guard: fewer than `min_screened_fraction` screened -> returns 2, `data_quality.failed.csv` written, previous `dashboard.html` and `digest.md` byte-identical.
   - a later good run removes `data_quality.failed.csv`; a demo run never touches `data_quality.csv`.

## Verification
Half 1: `pytest -q tests/test_cache.py tests/test_fx.py tests/test_validate.py tests/test_crosscheck.py tests/test_ownership.py` then the full suite.
Half 2: `pytest -q tests/test_pipeline_live.py`, the full suite, and `python -m dipdash --demo` (output unchanged). A planted bug (drop the `return 2`) must fail one test.

## Risks
- `cli.py` is in the hot group; half 2 must not overlap FE or other pipeline tasks. Half 2 must wait for half 1 to merge.
- The fake must mimic `yf.download` shapes only where `fetch_prices` parses them; that parsing (data.py:26-33) stays untested offline unless the fake also feeds a MultiIndex frame. I would add one small test for it.
- A fake that is too forgiving hides real Yahoo quirks (empty frames, tz-aware index), so `FakeYahoo` should offer a tz-aware mode.

## Requests to other owners
- orchestrator: `tests/test_sources.py` is not in `docs/agents/ownership.csv`; add it as data-engineer (or confirm the half-1 checks go elsewhere).
- integrator (half 2): everything in "Steps, half 2". Also `earnings.py` already has a `fetch=` seam, so it needs no change.
- test-engineer: none; `tests/synth.py` is only read.

## Open questions for Iiro
Q1 Bundle shape: (a) one `Sources` dataclass, recommended, one argument for tests; (b) separate keyword arguments on `main`; (c) a module-level registry patched with monkeypatch.
Q2 Should the cross-check (needs OpenBB) be part of the live-branch test? (a) skipped with its message, recommended; (b) faked via `Sources`; (c) both.
Q3 Should `fetch_prices` parsing be tested through a fake `yf.download` frame? (a) yes, one test, recommended; (b) no, only the seams.

**Needs a live run on Iiro's PC:** that `live_sources()` produces the same raw files and quality log as today, and a real `yf.download` shape matches the fake.

## Decision-log line
2026-11-04: Network access is injected through a typed `Sources` bundle (`sources.py`); `cli.main(sources=)` runs the live branch on fakes in tests, and `live_sources()` stays the default.

## Handoff
1. **Done:** `docs/plans/wave-2/DATA-1.md` (plan only).
2. **Checked:** read data.py, openbb_source.py, fx.py, cli.py:100-242, earnings.py seams, ownership.csv; no code run.
3. **Not checked:** everything above is unbuilt; live behaviour needs Iiro's PC.
4. **Requests to other owners:** see above.
5. **Decision-log line:** see above.
