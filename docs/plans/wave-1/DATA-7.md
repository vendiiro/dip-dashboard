# DATA-7 · one exchange registry

**Owner:** data-engineer · **Reviewer:** none required (no user-facing text) · **Skills:** `openbb-data-pull`, `engineering:architecture`, `engineering:testing-strategy` · **Size:** S (about 80 lines of code, 60 of tests)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
Add a leaf module `src/dipdash/exchanges.py` with a frozen `Exchange` record per Yahoo suffix (name, tz, regular close, currency,
OpenBB provider, country index). It replaces `SUFFIX_CURRENCY` (validate.py:24-25), `EXCHANGE_TZ` (earnings.py:25-27) and
`NORDIC_SUFFIXES` (openbb_source.py:10); those names stay as derived views, so callers do not change. The one intended behaviour
change: `.LS` gets `Europe/Lisbon` (today GALP.LS earnings times are converted in New York time). `DEFAULT_COUNTRY_INDICES`
(config.py:84-92) belongs to integrator and is requested, not edited.

## Steps
1. `exchanges.py` imports nothing from dipdash (no import cycle later). `Exchange(suffix, name, tz, close, currency, openbb, index)`,
   `EXCHANGES` with US under `""`, `suffix_of(ticker)` (no dot = US, so BRK-B is US), `exchange_for(ticker) -> Exchange | None`.
2. validate.py: `SUFFIX_CURRENCY` derived; `expected_currency` uses `exchange_for` (same output).
3. earnings.py: `EXCHANGE_TZ` derived; lines 132-133 become a pure `exchange_tz(ticker)` with the New York default.
4. openbb_source.py: `NORDIC_SUFFIXES` derived from `openbb == "nasdaq_nordic"`; `source_for` uses the registry.
5. `tests/test_exchanges.py`. Existing tests unchanged.

## Proposed registry (close times are regular session ends, local time; unverified, no code uses them yet)
| suffix | exchange | tz | close | ccy | OpenBB | index |
|---|---|---|---|---|---|---|
| "" (227) | NYSE/Nasdaq | America/New_York | 16:00 | USD | nasdaq | ^GSPC |
| .PA (24) | Euronext Paris | Europe/Paris | 17:30 | EUR | – | ^FCHI |
| .DE (22) | Xetra | Europe/Berlin | 17:30 | EUR | – | ^GDAXI |
| .ST (13) | Nasdaq Stockholm | Europe/Stockholm | 17:30 | SEK | nasdaq_nordic | ^OMXSPI |
| .SW (11) | SIX Swiss | Europe/Zurich | 17:30 | CHF | – | ^SSMI |
| .HE (9) | Nasdaq Helsinki | Europe/Helsinki | 18:30 | EUR | nasdaq_nordic | ^OMXH25 |
| .MI (9) | Borsa Italiana | Europe/Rome | 17:30 | EUR | – | – |
| .AS (8) | Euronext Amsterdam | Europe/Amsterdam | 17:30 | EUR | – | ^AEX |
| .MC (8) | BME Madrid | Europe/Madrid | 17:30 | EUR | – | – |
| .CO (7) | Nasdaq Copenhagen | Europe/Copenhagen | 17:00 | DKK | nasdaq_nordic | ^OMXC25 |
| .OL (5) | Oslo Børs | Europe/Oslo | 16:20 | NOK | – | OSEBX.OL |
| .BR (4) | Euronext Brussels | Europe/Brussels | 17:30 | EUR | – | – |
| .LS (1) | Euronext Lisbon | Europe/Lisbon | 16:30 | EUR | – | – |
| .L (0) | London SE | Europe/London | 16:30 | None (Q2) | – | – |

## Coverage found today
- `SUFFIX_CURRENCY` covers all 12 non-US suffixes. `EXCHANGE_TZ` **misses .LS** (the bug). `NORDIC_SUFFIXES` is correct (.OL is not served).
- .MI/.MC/.BR/.LS (22 tickers) have no country index and fall back to STOXX 600.
- No table records close times. CLAUDE.md's "Europe about 17:30 CET" is off for Helsinki (18:30 local), Oslo (16:20) and Copenhagen (17:00).

## Tests (offline)
- Derived views equal frozen copies of today's tables; the only allowed difference is `.LS: Europe/Lisbon` added.
- Every suffix in `config/universe.csv` has a valid ZoneInfo tz, a currency and a close time.
- Every registry index matches a configured index with the same suffix (no drift from config.py).
- `exchange_tz("GALP.LS") == "Europe/Lisbon"`; 20:30 New York on 2026-10-27 is 2026-10-28 in Lisbon.
- Unknown suffix: `exchange_for("X.ZZ") is None`; currency stays None; tz falls back to New York.

## Verification
`pytest -q tests/test_exchanges.py tests/test_validate.py tests/test_earnings.py tests/test_crosscheck.py tests/test_index_mapping.py tests/test_ownership.py`
(baseline for the existing five: 100 passed), then the full suite and the demo build.

## Requests to other owners
- integrator (after merge): build `DEFAULT_COUNTRY_INDICES` from `EXCHANGES[s].index`, same names and order.
- universe-curator: the registry gives the suffix → region and suffix → currency view `tests/test_universe.py` needs.
- docs-steward: CLAUDE.md's close-time line could name Helsinki 18:30 local (needs Iiro's approval).

## Risks
Close times are unverified (marked "verify"). Cached Lisbon earnings rows stay in New York time until their 7-day expiry.

## Open questions for Iiro
Q1 add country indices for Milan, Madrid, Brussels, Lisbon (FTSEMIB.MI, ^IBEX, ^BFX, PSI20.LS; needs a live check)?
Q2 should `.L` mean pence (GBp)? Q3 should an unknown suffix in earnings raise a warning instead of silently using New York time?

**Needs a live run on Iiro's PC:** close times, the GALP.LS earnings date after the fix, Yahoo symbols for any new indices.
