# Frontend contract: the hooks that tests and scripts depend on

Tests (`tests/test_browser.py`, `tests/visual/`) and `scripts/screenshots.py` find things on the page through the hooks below.
`tests/visual/test_contract.py` checks this file against `src/template.html` and the tests, so the two cannot drift:

- every hook listed here must exist in `src/template.html` (or, for `data:`, in `docs/payload.md`);
- every `#id`, `data-testid` and `data-*` attribute that a test or script uses must be listed here.

**Rule: change, rename or remove a listed hook only together with the test that uses it, in the same commit, and update this file.**
Adding a hook for a new test: add its row here first. Classes are checked one way only (listed -> exists).

Hook notation in the first column: `id:NAME` (element id), `testid:NAME` (`data-testid`), `attr:data-X` (a data attribute),
`class:NAME`, `window:NAME` (a global the page sets for tests), `data:NAME` (a field of the `DATA` payload; see `docs/payload.md`, not copied here).
The "Used by" column says which file would break: `browser` = `tests/test_browser.py`, `visual` = `tests/visual/vrlib.py`, `shots` = `scripts/screenshots.py`.

## Elements by id

| Hook | Used by | Meaning |
|---|---|---|
| `id:tiles` | browser, visual, shots | Container of the summary tiles; the page is "ready" when `#tiles .tile` exists |
| `id:brief` | browser | "Today in brief" paragraph |
| `id:head` | browser | Table header row (column count, sort clicks) |
| `id:sortsel` | browser | Phone sort select; its first option is "Size of drop (default)" |
| `id:body` | browser, visual | Table body; rows are `tr.row` |
| `id:cards` | browser, visual | Phone card list (shown at 600 px and below) |
| `id:empty` | browser, visual | Written empty state ("No stocks match ...") |
| `id:resetbtn` | browser | "Reset filters" button inside the empty state |
| `id:activebar` | browser | Chips for filters that differ from the default |
| `id:tabletitle` | browser | Table heading, changes with the filters |
| `id:sortnote` | browser | "Sorted by size of drop" beside the table title; visible only while no column is chosen (`S.sortKey` null) |
| `id:alerts` | browser | Trigger alerts section; each alert shows a badge worded from `context.setup_text` |
| `id:colbtn` | browser | "More columns" / "Fewer columns" toggle |
| `id:show` | browser | Show filter (dips meeting the check thresholds / all dips / all stocks), buttons carry `data-v` |
| `id:region` | browser, visual | Region filter, buttons carry `data-v` |
| `id:win` | browser, visual | "Drop measured over" select (`any`, `r1`, ...) |
| `id:drop` | browser, visual | Minimum drop slider |
| `id:droplab` | browser | Label of the minimum drop slider (hidden under the default rules) |
| `id:q` | browser, visual | Search box |
| `id:ctltoggle` | browser, visual | Phone "Filters" button that opens the controls |
| `id:dqbtn` | browser | Data-quality badge button (also shows "N stock(s) failed to draw"; wording for stocks without price data is "N without price data") |
| `id:dqpanel` | browser | Data-quality panel opened by `#dqbtn` |
| `id:stale` | browser | Stale-data banner element (FE-3) |
| `id:fail` | browser, visual | Visible failure alert (FE-4) |
| `id:hist` | browser | Histogram of today's moves |
| `id:sect` | browser | Sector breakdown chart |

## Hooks by `data-testid`

| Hook | Used by | Meaning |
|---|---|---|
| `testid:stale` | browser | The stale banner, visible only when prices are over 2 weekdays old on a non-demo page |
| `testid:fail` | browser | The failure alert |
| `testid:tile-quality` | browser | Dips-meeting-the-check-thresholds tile; its `.big` equals the rows ranked `Quality dip` (shown as "Dips meeting the check thresholds") |
| `testid:tile-new` | browser | New-since-yesterday tile; chips equal the rows marked new |
| `testid:tile-knife` | browser | Falling-knife tile |
| `testid:tile-market` | browser | Market-context tile |
| `testid:tile-chip` | browser | One ticker chip inside a tile |
| `testid:tile-chip-more` | browser | The "+N more" button of a tile |
| `testid:new-badge` | browser | The NEW badge in a row or card |
| `testid:cards-more` | browser | "Show all N stocks" button under the phone cards |

## Data attributes

| Hook | Used by | Meaning |
|---|---|---|
| `attr:data-testid` | browser | See the table above |
| `attr:data-v` | browser, visual | Value of a filter button (`all`, `dips`, `quality`, `US`, `Nordic`, ...) |
| `attr:data-t` | browser | Ticker on a table row (`tr.row[data-t]`) and on a card |
| `attr:data-k` | browser | Column key on a table cell (`td[data-k=price]`) |
| `attr:data-dir` | browser | Direction (`up` / `down`) of the end dot on sparklines and detail charts |

## Classes

| Hook | Used by | Meaning |
|---|---|---|
| `class:row` | browser, visual | A table row for one stock (`tr.row`); `open` is added while its detail is shown |
| `class:open` | browser, visual | The expanded row or card |
| `class:detail` | browser, visual | The detail cell under an open row (`td.detail`) |
| `class:tkbtn` | browser | The ticker button in a row (tap target of at least 40 px) |
| `class:sc` | browser, visual | One phone card |
| `class:schead` | visual | The tappable head of a phone card |
| `class:tile` | browser, shots | A summary tile |
| `class:big` | browser | The large number in a tile |
| `class:ct` | browser | The live count beside a filter option |
| `class:enddot` | browser | End dot of a sparkline or chart |
| `class:extra` | browser | Detail content behind "More context" |
| `class:axcap` | browser | Axis caption of the detail chart (names the currency) |
| `class:foot` | browser | Small foot note style inside the detail |
| `class:s-crit` | browser | State class on `#dqbtn` when something failed |

## Window hooks

| Hook | Used by | Meaning |
|---|---|---|
| `window:__dipView` | browser | `__dipView(ticker)` returns the view the page computed for a row (its `rank`) |

## `DATA` fields the tests read

Meaning and types are in `docs/payload.md`; only the integrator renames them.

| Hook | Used by | Meaning |
|---|---|---|
| `data:rows` | browser, visual | List of stock rows |
| `data:demo` | browser, visual | True for demo pages; the stale banner is off then |
| `data:generated` | visual | Build time text; the visual tests pin it |
| `data:t` | browser | Ticker of a row |
| `data:region` | browser | Region of a row |
| `data:dip` | browser, visual | Row passes the default dip rule |
| `data:setup` | browser | Stable setup enum of a row (key on it, never show it) |
| `data:setup_text` | browser | Reader-facing setup text ("Dip · passes 5 of 6 scored checks", "... (2 no data)", "Dip · data looks unreliable"); what the badge shows at the nightly label; under other controls the page builds the same format from `q_passed`, `q_scored`, `q_applicable`. Alerts show `context.setup_text`, keyed on `context.setup` |
| `data:q_status` | browser | `ok`, `thin`, `distorted` or `no_data`; the test sets `distorted` to check the page's wording |
| `data:q_why` | browser | Reason shown in the badge tooltip and the detail when `q_status` is `distorted` |
| `data:spark` | browser, visual | 90-day sparkline values (set to null by the failure tests) |
| `data:hist` | browser | One-year history of a row (`c` = closes) |
| `data:asof` | browser | Date of the last bar of a row |
| `data:ccy` | browser | Price currency of a row |

## Visual baselines

`tests/visual/baseline/*.png` pin 12 states (default and detail at 1280 and 390 px in light and dark; filters, empty, stale and
failure once each) with a fixed demo page, a fixed clock and no web fonts. They are made in the Linux build container; other
systems skip the compare. A deliberate design change fails them on purpose: run
`python scripts/screenshots.py --states all --update`, look at the new images and review the diff before committing them.
Never run `--update` in CI. Limits: more than 0.1% of pixels changed by more than 8/255 in any channel.
