# The payload: the contract between the Python side and the page

`dipdash.dashboard.build_payload` builds one JSON object; `cli.py` adds `alerts`; `template.html` receives it as `DATA`.
Only the integrator renames or removes a field. Any change here goes together with `tests/test_payload_contract.py`, which
parses the tables below and compares them with a real demo run (`python -m dipdash --demo`) and with what the template reads.

## Conventions

- **Moves are fractions, not percent.** `-0.04` means -4%. This holds for `r1`, `r5`, `r21`, `dd20`, `dd52`, `vs200`, `x5`, `res1`, `res5`
  and the index moves.
- `price` is the adjusted close in the stock's local currency (`ccy`). `fx_to_usd` gives USD per one unit of each currency.
- **Null** (`yes` in the Null column) means the value could not be computed or was not available; the page shows a dash. NaN and
  infinity never reach the JSON: they become null. `optional` means the key may be missing.
- Types are `str`, `int`, `float`, `bool`, `list`, `dict`. JSON does not tell `1.0` from `1`, so a whole number is accepted where `float` is documented.
- In the demo the residual, beta, earnings and index-reason fields are always null; their types come from the code.

## Top level

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `generated` | str | no | `YYYY-MM-DD HH:MM` | build time in time zone `tz` |
| `tz` | str | no | IANA zone | the schedule's time zone |
| `demo` | bool | no | | true for synthetic demo data |
| `rows` | list | no | | one row per screened stock (see Row) |
| `data_quality` | list | no | | stocks left out of the screen (see Left-out item) |
| `chart_dates` | list | no | `YYYY-MM-DD` | the shared date axis of every row's `hist`: sorted union of the rows' bar dates, oldest first, no duplicates; empty when there are no rows |
| `price_scale` | int | no | | 100: `hist` and `spark` prices are integers in 1/`price_scale` of the currency unit (hundredths); divide by it to get the price |
| `fx_to_usd` | dict | no | USD per 1 unit | currency code to rate; empty in the demo |
| `indices` | list | no | | market-context indices (see Index item) |
| `issues` | list | no | | data-quality findings (see Issue item) |
| `settings` | dict | no | | `dip`, `quality`, `knife`: the thresholds used (see Settings) |
| `alerts` | list | yes | | trigger alerts, see below |

**`alerts` has three states.** Key absent: the alert step did not run (a payload built by `build_payload` alone). `null`: the step
failed, which is not the same as no alerts. `[]`: it ran and the day is quiet. The template reads these the same way.

## Row

One entry of `rows`. Keys are exactly these.

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `t` | str | no | | ticker (Yahoo style, with exchange suffix) |
| `name` | str | no | | company name |
| `region` | str | no | | universe region: US, Europe or Nordic |
| `sector` | str | no | | sector from the universe file (may be empty text) |
| `asof` | str | no | `YYYY-MM-DD` | date of the stock's last bar |
| `price` | float | yes | local currency | last adjusted close |
| `r1` | float | yes | fraction | 1-day move |
| `r5` | float | yes | fraction | 5-day move |
| `r21` | float | yes | fraction | 21-day move |
| `dd20` | float | yes | fraction | distance below the 20-day high (0 or negative) |
| `dd52` | float | yes | fraction | distance below the 52-week high (0 or negative) |
| `vs200` | float | yes | fraction | price relative to the 200-day average (-0.1 = 10% below) |
| `rsi` | float | yes | 0 to 100 | 14-day RSI |
| `z5` | float | yes | standard deviations | 5-day move divided by its usual size for this stock |
| `volx` | float | yes | multiple | last volume over its 20-day average; null without volume |
| `x5` | float | yes | fraction | 5-day move minus the index's 5-day move |
| `res1` | float | yes | fraction | 1-day move after removing the market-beta part |
| `res5` | float | yes | fraction | 5-day move after removing the market-beta part |
| `res5z` | float | yes | standard deviations | `res5` scaled by residual volatility |
| `beta` | float | yes | ratio | market beta used (clipped to the allowed range) |
| `beta_raw` | float | yes | ratio | fitted beta before clipping |
| `beta_side` | str | yes | `floor` or `cap` | which limit clipped the beta; null if not clipped |
| `beta_se` | float | yes | ratio | standard error of the fitted beta; null if no residual |
| `mkt_adj` | bool | no | | true only if the beta was not capped or floored and `beta_se` is at most 0.25; false when there is no residual |
| `res_why` | str | yes | | why the residual fields are null; null when they are present |
| `s200_falling` | bool | no | | the 200-day average is lower than 20 bars ago |
| `knife` | bool | no | | falling-knife flag (below a falling 200-day average and far below the 52-week high) |
| `partial` | bool | no | | last bar is dated today, so the session may still be open |
| `dip` | bool | no | | meets the dip rule (see `why`) |
| `why` | list | no | | text reasons the dip rule fired; empty when `dip` is false |
| `spark` | list | no | 1/`price_scale` of local currency | last 90 closes for the small chart, oldest first, as integers (12345 = 123.45); no dates, never null |
| `hist` | dict | no | | longer series for the detail chart (see Hist) |
| `prev` | dict | yes | | metrics at the previous close (see Prev); null with too little history |
| `idx` | str | yes | | name of the market-context index used |
| `idx_sym` | str | yes | | Yahoo symbol of that index |
| `idx_why` | str | yes | | why `x5` is null; null when `x5` is present |
| `earn` | dict | yes | | earnings context (see Earn); null when earnings were not loaded (always in the demo) |
| `q` | int | yes | 0 to 100 | quality score: share of the applicable checks passed (0 to 100); null when too few checks have data |
| `qchecks` | list | no | | the six checks (see Quality check) |
| `q_scored` | int | no | count | quality checks that had data (of the applicable ones); shown as "scored on n/6" |
| `q_applicable` | int | no | count | 6 minus the checks that do not apply to the sector (4 for Financials) |
| `q_passed` | int | no | count | applicable checks passed |
| `q_status` | str | no | | evidence behind `q`: `ok`, `thin` (scored fewer than applicable), `distorted` (see `q_why`) or `no_data` (`q` is null); precedence no_data, distorted, thin, ok |
| `q_why` | str | yes | | plain-language reason when `q_status` is `distorted` (for example ROE above the limit, or ROE and debt/equity both missing); null otherwise |
| `q_must_failed` | list | no | | names of must-pass rules that failed (for example `net_margin_positive`); empty list when none. A failure makes `setup` `Dip, low quality` whatever `q` is |
| `q_must_missing` | list | no | | names of must-pass rules whose data is missing; missing is not a failure |
| `fpe` | float | yes | ratio | forward price/earnings |
| `tpe` | float | yes | ratio | trailing price/earnings |
| `ccy` | str | no | currency code | currency of `price`; empty text if unknown |
| `news` | list | no | | recent headlines for fallers (see Headline); third-party text |
| `setup` | str | no | | one of `Quality dip`, `Falling knife`, `Dip, low quality`, `Dip, no fundamentals`, `No dip`; the stable key, never reworded. `Quality dip` = a dip whose quality score meets the minimum and net margin is above 0 (shown as "Dip · passes N of M scored checks"); `Falling knife` = a dip that also meets the falling-knife condition; `Dip, low quality` = a dip whose quality score is below the minimum or a must-pass rule failed; `Dip, no fundamentals` = a dip with missing or distorted fundamentals; `No dip` = the dip thresholds were not met. It can differ for the same `q`: distorted fundamentals give `Dip, no fundamentals`, a failed must-pass rule gives `Dip, low quality` |
| `setup_text` | str | no | | reader-facing text for `setup`; show this, key on `setup`. For `Quality dip` and `Dip, low quality`: "Dip · passes N of M scored checks" (N = `q_passed`, M = `q_scored`), with " (K no data)" appended when K = `q_applicable` − `q_scored` > 0, e.g. "Dip · passes 5 of 6 scored checks" or "Dip · passes 3 of 4 scored checks (2 no data)"; plain "Dip" when no counts exist. `Dip, no fundamentals` reads "Dip, no fundamentals", or "Dip · data looks unreliable" when `q_status` is `distorted`. `Falling knife` and `No dip` are unchanged. Enum-level labels for lists: `Quality dip` = "Dip, more checks passed", `Dip, low quality` = "Dip, fewer checks passed" (`SETUP_LABELS` in `screen.py`) |

## Hist

The detail chart's series. They carry **no dates of their own**: they sit on the top-level shared axis `chart_dates`.

**Mapping rule.** Item `i` of `c`, `s` and `h` belongs to the date `chart_dates[o + i]`. So the first bar is `chart_dates[o]`, and
the lists end at the stock's last bar, `chart_dates[o + len(c) - 1]`, which equals the row's `asof`. All three lists have the same
length, and `o + len(c) <= len(chart_dates)` (a stock whose last bar is a few days old ends before the end of the axis). Inside
that range an entry is null where the axis has a date on which this stock had no bar (an exchange holiday), in `c` and in `s`
and `h` alike; skip those entries when drawing. Prices are integers in hundredths (see `price_scale`): `c[i] / price_scale` is the
close, with the same 2-decimal rounding as before. Before this change each row had its own `d` list of dates (252 of them) and floats.

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `o` | int | no | index | position in `chart_dates` of this row's first bar (0 or more) |
| `c` | list | no | 1/`price_scale` of local currency | closes; null on an axis day without a bar for this stock |
| `s` | list | no | 1/`price_scale` of local currency | 200-day average; null entries until it can be computed, and on days without a bar |
| `h` | list | no | 1/`price_scale` of local currency | rolling 52-week high; null entries until it can be computed, and on days without a bar |

## Prev

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `r1` | float | yes | fraction | 1-day move at the previous close |
| `r5` | float | yes | fraction | 5-day move at the previous close |
| `r21` | float | yes | fraction | 21-day move at the previous close |
| `dd20` | float | yes | fraction | distance below the 20-day high at the previous close |
| `knife` | bool | no | | falling-knife flag at the previous close |
| `dip` | bool | no | | dip rule at the previous close |

## Earn

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `last` | str | yes | `YYYY-MM-DD` | last report date (null if unknown or not trusted) |
| `next` | str | yes | `YYYY-MM-DD` | next report date (null if unknown or not trusted) |
| `days_since_last` | int | yes | trading days | from `last` to the data date |
| `days_until_next` | int | yes | trading days | from the data date to `next` |
| `label` | str | no | | `reported_recently`, `reports_soon` or `none` |
| `note` | str | no | | plain-language explanation, may be empty |
| `estimated` | bool | no | | the next date is an estimate |
| `stale` | bool | no | | a refresh failed and older data is shown |
| `error` | str | yes | | why the earnings pull failed |
| `fetched_at` | str | yes | timestamp | when the data was fetched |

## Quality check

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `label` | str | no | | check description with its threshold |
| `key` | str | no | | fundamentals field it reads |
| `ok` | bool | yes | | passed; null = no data or not applicable |
| `value` | float | yes | field's own unit | the number checked |
| `na` | bool | optional | | present and true when the check does not apply to the stock's sector |

## Headline

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `title` | str | no | | headline text (untrusted third-party text) |
| `src` | str | no | | publisher |
| `url` | str | no | | link; may be empty |

## Index item

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `symbol` | str | no | | Yahoo symbol |
| `name` | str | no | | display name |
| `region` | str | no | | universe region it gives context for |
| `price` | float | yes | index points | last level |
| `r1` | float | yes | fraction | 1-day move |
| `r5` | float | yes | fraction | 5-day move |
| `asof` | str | no | `YYYY-MM-DD` | date of its last bar |

## Issue item

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `ticker` | str | no | | ticker, or `*` for a whole-run finding |
| `check` | str | no | | check name, for example `partial_bar` |
| `severity` | str | no | | `error`, `warn` or `info` |
| `detail` | str | no | | plain-language detail |

Since the data-guard wiring the live run adds these `check` values to `issues` (no new field; the page's data-quality badge counts them
like any other issue). They never stop the run; exit code 2 is kept for "too few stocks screened" only.
`exchange_missing` (error, ticker is the suffix label such as `.ST`), `fx_missing` (error, ticker is the currency),
`fundamentals_coverage` (error overall, warn for one exchange), `lagging_vs_peers`, `partial_bar` (judged by each exchange's close time),
`fetch_failed` (error if the ticker has no bars, else warn), `fundamentals_stale`, `fundamentals_missing`, `exchange_thin` (warn),
`earnings_coverage` (info). Demo runs carry none of the live-only ones (FX, fetch, coverage).

**Not in the payload:** the coverage table. A live run writes it to `output/run_meta.json`
(`asof`, `generated`, `universe`, `screened`, `issue_counts`, `coverage.summary`, `coverage.rows`; row keys are `coverage.COLUMNS`)
and to the digest ("Data coverage by exchange"). A demo run writes neither.

## Left-out item

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `t` | str | no | | ticker |
| `reason` | str | no | | `no_price_data`, `short_history` or `stale` |
| `detail` | str | no | | plain-language detail |

## Settings

`settings` has three dicts, copied from `config/settings.toml`: `dip` (`drop_1d`, `drop_5d`, `drawdown_20d`, fractions),
`quality` (`min_score`, `roe_min`, `margin_min`, `debt_to_equity_max`, `market_cap_min`, `must_pass`, `distorted_roe_above`) and `knife` (`below_200d_falling`,
`drawdown_52w`). The page reads `dip.drop_5d` and `quality.min_score`.

- `quality.must_pass`: list of str, never null; named rules (`net_margin_positive`, `fcf_positive`), default `["net_margin_positive"]`. A failed rule means the setup cannot be `Quality dip` (it becomes `Dip, low quality`); missing data is not a failure. A definition, not a tested filter.
- `quality.distorted_roe_above`: float (fraction, 1.0 = 100%), never null; ROE above this marks the fundamentals `distorted`.

## Alert item

| Field | Type | Null | Unit | Meaning |
|---|---|---|---|---|
| `ticker` | str | no | | ticker, or `*` for the first-run summary |
| `name` | str | no | | company name; empty for the summary |
| `condition` | str | no | | internal condition key. `recovery` and `rsi_rebound` are old names kept so saved alert state and `config/alerts.toml` still work; their visible text is "back above its 20-day average" and "RSI back above 30". Show `headline`, not the key |
| `kind` | str | no | | `info` or `caution` |
| `headline` | str | no | | one-line text |
| `detail` | str | no | | why it was raised |
| `context` | dict | no | | a few row values for reference (`price`, `r1`, `r5`, `res5`, `q`, `setup`, `setup_text`); empty for the summary. `setup` is the stable enum key, `setup_text` the reader-facing text (same as the row field; show it, key on `setup`); null if the row had none |
| `asof` | str | no | `YYYY-MM-DD` | data date |
| `note` | str | optional | | extra caveat when there is one |

## Changing the payload

1. Edit `build_payload` (or `cli.py`), this file and the contract test in the same commit.
2. Tell ui-builder, who lists the page's DOM hooks in `docs/frontend-contract.md`.
3. The test fails on a renamed or removed field, a changed type, an undocumented key, or a template read of an undocumented field.
