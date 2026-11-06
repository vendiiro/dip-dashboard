# Frontend contract: the hooks that tests and scripts depend on

## Where the page lives and how to edit it

`src/template.html` is **generated**. Edit the parts in `src/web/`, then run `python src/web/assemble.py --write` and commit both.
`tests/test_web_build.py` fails when the template is out of date or a part is missing from `src/web/manifest.txt`.
The page stays one self-contained file (CSS and JavaScript inlined), so `dashboard.render_html` is unchanged.

| Part | Holds |
|---|---|
| `head.html` | `<!doctype>` to the font links |
| `tokens.css` | colour, font and dark-mode variables (dark defined once) |
| `layout.css` | reset, page width, headings, focus ring |
| `components.css` | every component, in the order of the page (later rules win, so keep the order) |
| `responsive.css` | media queries (1100, 900, 600, 480 px, reduced motion); must stay last |
| `body.html` | the markup, `<body>` to the tooltip element |
| `data.js` | the one `const DATA = __DATA__;` line |
| `core.js` ... `main.js` | one script in a single `(() => { try { ... } })()`; `core.js` opens the wrapper, `helpers.js` opens `try {`, `main.js` closes both. Sections: `core` (failure box, `guard`), `helpers` (state, formatters, windows), `header` (data quality, stale banner), `footer` (definitions), `setup`, `brief`, `alerts`, `tiles`, `filters` (active chips), `table`, `cards` (phone), `detail`, `charts` (tooltip, price chart, histogram, sectors), `controls`, `main` (first draw) |
| `fallback.js` | second script that reports a data file that could not be read |
| `manifest.txt` | build order; each part exactly once |

To add a part: create the file, add a line to `manifest.txt` (`css`/`js` role), run the assembler. Parts are not valid files on their own
(the wrapper braces open and close across files), so check the assembled page: `node --check` does not apply, the browser tests do.

Tests (`tests/test_browser.py`, `tests/visual/`) and `scripts/screenshots.py` find things on the page through the hooks below.
`tests/visual/test_contract.py` checks this file against `src/template.html` and the tests, so the two cannot drift:

- every hook listed here must exist in `src/template.html` (the generated page; its source is `src/web/`) (or, for `data:`, in `docs/payload.md`);
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
| `id:body` | browser, visual | Table body; rows are `tr.row`. Built on desktop only (empty on a phone), and only the first 25 rows until "Show all N stocks" is pressed |
| `id:cards` | browser, visual | Phone card list (shown at 600 px and below). Built on a phone only (empty on desktop); first 10 cards until "Show all N stocks" |
| `id:rowsmore` | browser | Bar under the desktop table with "Showing the first 25 of N stocks." and the show-all button; hidden when the list has 25 rows or fewer, and on a phone |
| `id:empty` | browser, visual | Written empty state ("No stocks match ...") |
| `id:resetbtn` | browser | "Reset filters" button inside the empty state |
| `id:activebar` | browser | Chips for filters that differ from the default |
| `id:tablehint` | browser | Hint line beside the table title: how to open a row and sort, and the mini chart (90-day, own low and high) wording; shorter on a phone |
| `id:tabletitle` | browser | Table heading, changes with the filters |
| `id:sortnote` | browser | "Sorted by size of drop" beside the table title; visible only while no column is chosen (`S.sortKey` null) |
| `id:alerts` | browser | Trigger alerts section; each alert shows a badge worded from `context.setup_text` |
| `id:colbtn` | browser | "More columns" / "Fewer columns" toggle |
| `id:controls` | browser | The filter box; two short rows on desktop, the panel behind `#ctltoggle` on a phone |
| `id:show` | browser | Show filter (dips meeting the check thresholds / all dips / all stocks), buttons carry `data-v` |
| `id:region` | browser, visual | Region filter, buttons carry `data-v` |
| `id:win` | browser, visual | "Drop measured over" select (`any`, `r1`, ...) |
| `id:drop` | browser, visual | Minimum drop slider |
| `id:droplab` | browser | Label of the minimum drop slider (hidden under the default rules) |
| `id:q` | browser, visual | Search box |
| `id:ctltoggle` | browser, visual | Phone "Filters" button that opens the controls |
| `id:ctlsum` | browser | Summary on that button, e.g. "All dips · All · Quality score ≥ 60" |
| `id:scrollcue` | browser | "Scroll sideways for more columns ›" cue above the table; visible only while the table scrolls sideways (`.scroll.hs`) |
| `id:dqbtn` | browser | Data-quality badge button (also shows "N stock(s) failed to draw"; wording for stocks without price data is "N without price data") |
| `id:dqpanel` | browser | Data-quality panel opened by `#dqbtn` |
| `id:stale` | browser | Stale-data banner element (FE-3) |
| `id:fail` | browser, visual | Visible failure alert (FE-4) |
| `id:hist` | browser | Histogram of today's moves |
| `id:sect` | browser | Sector breakdown chart |
| `id:defs` | browser | The `<details>` that holds the definitions; closed by default at every width. Links to `#def-...` open it, scroll the term heading (`<dt>`) into view, highlight `<dt>` and `<dd>` with `.hit`, and move focus to the `<dd>` |
| `id:def-q` | browser | Quality score definition; target of the "Definitions" link in the brief |
| `id:def-setup` | browser | Setup label definition (opened by `#def-setup` links and URLs) |
| `id:def-res` | browser | Definition of "5d vs index, beta-adjusted (residual)"; its `<dt>` follows the plain "5d vs index" entry |
| `id:def-beta` | browser | The one plain-words definition of beta |
| `id:def-idx` | browser | Definition of the plain "5d vs index" difference (listed before the residual entry) |

## Hooks by `data-testid`

| Hook | Used by | Meaning |
|---|---|---|
| `testid:stale` | browser | The stale banner, visible only when prices are over 2 weekdays old on a non-demo page |
| `testid:fail` | browser | The failure alert |
| `testid:tile-quality` | browser | Dips-meeting-the-check-thresholds tile; its `.big` equals the rows ranked `Quality dip` (shown as "Dips meeting the check thresholds"); its `.foot` reads "N of M dips have quality score ≥ Q and net margin above 0 · drop window: default" (or "chosen window"), where M is the "All dips" count |
| `testid:tile-new` | browser | New-since-the-previous-close tile (label "New since the previous close"); chips equal the rows marked new |
| `testid:tile-knife` | browser | Falling-knife tile |
| `testid:tile-market` | browser | Market-context tile |
| `testid:tile-market-line` | browser | One line in the Market tile, shown at 480 px and below only (where the brief's `.idxline` is hidden): "Median stock −0.7% (5d) · 52 of 55 dips fell 5+ points more than their index", built by the same `mktFacts` as the brief |
| `testid:tile-chip` | browser | One ticker chip inside a tile |
| `testid:tile-chip-more` | browser | The "+N more" button of a tile |
| `testid:new-badge` | browser | The NEW badge in a row or card |
| `testid:defs` | browser | The Definitions `<details>` (same element as `#defs`) |
| `testid:defs-toggle` | browser | Its `<summary>` ("Definitions", at least 40 px tall) |
| `testid:foot-always` | browser | Sources and "Not investment advice", always visible outside the toggle |
| `testid:cards-more` | browser | "Show all N stocks" button under the phone cards (first 10 shown; label "Show the first 10 only" when expanded) |
| `testid:rows-more` | browser | The same button under the desktop table (first 25 rows shown; "Show the first 25 only" when expanded). Same state and style as `cards-more`; any filter or sort change folds the list back; an open row outside the first 25 stays drawn |

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
| `class:dwrap` | browser | Wrapper inside `td.detail`. While the table scrolls sideways (`.hs`) it is sticky at the left edge and as wide as the scroll box (`--boxw`), so an open detail never exceeds the visible box |
| `class:tkbtn` | browser | The ticker button in a row (tap target of at least 40 px) |
| `class:sc` | browser, visual | One phone card |
| `class:scroll` | browser | Wrapper of the table. While the table fits the card it is not a scroller and the header is plain CSS `position: sticky; top: 0` on the page scroll |
| `class:hw` | browser | Header cell whose name wraps (max 110 px): the residual column shows "5d vs index (β-adj.)", the full name is in its tooltip, the definitions footer and the detail row |
| `class:hs` | browser | Added to `.scroll` when the table is wider than the card (More columns, narrow windows): it scrolls sideways and the header is pinned by JS (`--pin`) instead |
| `class:schead` | visual | The tappable head of a phone card |
| `class:tile` | browser, shots | A summary tile |
| `class:big` | browser | The large number in a tile |
| `class:ct` | browser | The live count beside a filter option |
| `class:enddot` | browser | End dot of a sparkline or chart |
| `class:extra` | browser | Detail content behind "More context" |
| `class:axcap` | browser | Axis caption of the detail chart (names the currency) |
| `class:hit` | browser | Highlight on the `<dt>` and `<dd>` of the definition a link jumped to |
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

## Layout limits the browser tests pin (FE-1, FE-2)

- 1280 x 800, demo page: the first table row starts below 900 px from the page top (755 px now; 707 px on the 4 Nov snapshot data); the filters take two rows (`#controls` under 130 px tall).
- 390 x 844, demo page with its Demo banner: the first card starts less than 910 px from the top (903 px now; it was 831 px before the Market tile line was added, so on the demo page it is now just below the 844 px fold).
- The header row `#head th` stays at the top of the viewport while the page scrolls, light and dark, also with More columns.
- Only the layout in use is built: desktop has `tr.row` and no `.sc`, phone has `.sc` and no `tr.row`; `#head` is built on both.
- Tests that read every row on desktop press `rows-more` first (helper `expand_rows` in `tests/test_browser.py`).

- 1024 and 1100 px, demo page: the default table (10 columns) fits the card without sideways scroll (`.scroll` has no `.hs`), and a price cell is never clipped or covered by the pinned Stock column. Below 1100 px cells use 5 px side padding and the Setup badge may wrap to two lines.
- With More columns the table scrolls inside its box; the pinned Stock column is opaque and has an edge line and shadow; no header cell except Stock and Setup is wider than 130 px; sortable headers and `.tkbtn` are at least 40 px wide.
- At 390 px the Market tile ends with the `tile-market-line` sentence; it is hidden on desktop, where the brief says the same.

## Visual baselines

`tests/visual/baseline/*.png` pin 12 states (default and detail at 1280 and 390 px in light and dark; filters, empty, stale and
failure once each) with a fixed demo page, a fixed clock and no web fonts. They are made in the Linux build container; other
systems skip the compare. A deliberate design change fails them on purpose: run
`python scripts/screenshots.py --states all --update`, look at the new images and review the diff before committing them.
Never run `--update` in CI. Limits: more than 0.1% of pixels changed by more than 8/255 in any channel.
