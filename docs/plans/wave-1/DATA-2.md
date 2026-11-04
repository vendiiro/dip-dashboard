# DATA-2 · offline universe tests + a live ticker check

**Owner:** universe-curator · **Reviewer:** stats-reviewer (coverage) · **Skills:** `openbb-data-pull`, `data:validate-data`, `engineering:testing-strategy` · **Size:** M (test S; script and its fake-based tests M)
**Planned 2026-11-04 (plan only; nothing changed yet).**

## Understanding
`tests/test_universe.py` guards `config/universe.csv` offline. `scripts/verify_universe.py` is run once by Iiro on his PC and
writes `config/universe_verified.csv` with a status per ticker. It never removes a ticker; that is decision D4. The suffix list
is a small temporary copy until DATA-7 (exchange registry) lands.

## Offline checks, and today's result on the 348 rows
| Check | Rule | Today |
|---|---|---|
| a. suffix known | no suffix, or one in `SUFFIX_CURRENCY` (fallback set marked `TODO(DATA-7)`) | pass (.PA 24, .DE 22, .ST 13, .SW 11, .HE 9, .MI 9, .AS 8, .MC 8, .CO 7, .OL 5, .BR 4, .LS 1) |
| b. region matches suffix | none = US; .HE .ST .CO .OL = Nordic; others = Europe | pass (227 / 87 / 34) |
| c. sector | one of 11 fixed labels | pass |
| d. format | `^[A-Z0-9]{1,6}(-[A-Z]{1,3})?(\.[A-Z]{2})?$`, no stray whitespace | pass |
| e. duplicate names | exact match after removing legal suffixes and punctuation | pass (Nestle/Neste is a near match only, allow-listed) |
| f. share classes | one line per company (no GOOG + GOOGL, no ADR + home line) | pass |

Each check also gets a planted-bad-row test on a `tmp_path` CSV (`BRK.B`, `X.L`, a Nordic row labelled Europe, `Tech `, two Alphabet lines).

## Script
`python scripts/verify_universe.py [--universe …] [--out config/universe_verified.csv] [--tickers A,B] [--limit N] [--batch 50] [--sleep 2.0] [--min-cap-usd 20e9]`
- Columns: ticker, csv_name, yahoo_long_name, name_score, quote_type, exchange, currency, expected_currency, first_bar, last_bar, bar_count, market_cap_usd, status, detail, verified_at.
- Status (several joined by `;`): ok, no_bars, stale (last bar more than 4 trading days old), not_equity, name_mismatch (difflib < 0.6), currency_mismatch, under_20b, duplicate_name, fetch_error.
- Bars by `yf.download` in batches of 50; names and types from `Ticker.info` one at a time with 3 retries and backoff; market cap converted with `fx.py`. Results are written row by row so a re-run resumes.
- Exit code 0 even with flags; 2 if the network failed for more than half the tickers. Pure logic (`classify_row`, `name_score`) is kept apart from the fetch and tested offline with fakes.

**On Iiro's PC:** `.venv\Scripts\python.exe scripts\verify_universe.py --limit 10` first, then without `--limit` (about 15 minutes).

## Steps
1. Write the test (green straight away), commit. 2. Write the script with fake-based tests, commit.

## Verification
`pytest tests/test_universe.py tests/test_config.py tests/test_ownership.py -q`; `python scripts/verify_universe.py --help`; a fake test for every status value.

## Risks
Yahoo rate limits on 348 `.info` calls (batches, sleep, backoff, resume). yfinance is not installed in the sandbox, so the live part
is unchecked here. The 59 US rows added today are unverified (a hunch: DOW may flag `under_20b`). Survivorship is RES-10, not this task.

## Requests to other owners
- data-engineer (DATA-7): expose a suffix → region and suffix → currency view so the test can drop its fallback; make Oslo's missing OpenBB provider explicit.

## Open questions for Iiro
1. Name-mismatch threshold 0.6, or report the score only? 2. `under_20b` uses today's market cap (not point-in-time): fine?
3. Commit `config/universe_verified.csv`? (Assumed yes.) 4. Should a no-suffix ticker listed outside the US count as US? (Proposed no.)
