# Market context: per-country index, 5-day move on the stock's own date

- Date: 2026-11-04
- Topic: dashboard
- Origin: migrated, old entry 49 of 54 (text verbatim)

---

- 2026-11-04 (market context) "5d vs index" was blank for 23 of 59 rows (every Europe/Nordic row whose latest Yahoo bar lagged). CAUSE: not the region mapping (every Europe/Nordic region had an index) and not currency, but a date mismatch.
  The batch Yahoo pull returned NaN for the latest day on most European lines (the stock's last real bar was 2026-11-02; Nasdaq Nordic cross-check already showed 11-03 existed), while each index is fetched on its own and had 11-03.
  `build_payload` demanded index asof == stock asof, so the cell fell back to "-". Second flaw: every Nordic stock (.ST/.CO/.OL too) was compared with the Helsinki index.
  FIX: (a) per-country mapping by ticker suffix (`suffixes` on an index entry; new `[[country_indices]]` and `[context] fallback_region`), order suffix -> region index -> Europe-wide fallback -> "-" with a written reason (`idx_why`);
  (b) the index's recent closes (12) ride in the payload and the index 5-bar move is taken ENDING ON THE STOCK'S OWN LAST BAR DATE, so a stock a day behind is still compared like for like (no number if that date is absent).
  Edits outside the agreed list, minimal and needed: `data.fetch_indices` (adds `closes`) and `cli.py` (fetches `settings.all_indices`, and the index_missing wording). Backups in the scratchpad `backup2/`.
  Retest on Yahoo 2026-11-04, 1y daily bars (n, last bar, gaps over 4 calendar days; all gaps seen are 5-6 day holiday weekends): ^GSPC 251, 11-03, none; ^STOXX 251, 11-03; ^STOXX50E 251, 11-03; ^OMXH25 251, 11-03;
  ^OMXC25 243, 11-03 (fewer bars: Danish holidays; no gap over 6 days); ^OMXS30 1 bar (UNUSABLE, as before); ^OSEBX 404 (UNUSABLE, as before); ^OMXSPI 251, 11-03 (USED for .ST); OSEBX.OL 251, 11-03 (USED for .OL);
  ^AEX 256, ^GDAXI 254, ^FCHI 256, ^SSMI 251, all 11-03 (USED for .AS .DE .PA .SW); EWD and EWN (USD ETFs) 251, 11-03 but NOT used: a USD ETF's % move contains the USD/SEK or USD/NOK move, so it is not the local market.
  No bar over 5.1% in a day in any kept index. OpenBB 5.0.0 default bundle has no index route (`obb.index` absent), so indices stay Yahoo-only. ^STOXX50E (large-cap Eurozone) fetched fine but is not mapped to anything.
  Currency: a stock's 5-day % move against a local index's 5-day % move is unitless and same-currency, so no FX step is needed. Caveats: ^GDAXI is a total-return index (dividends reinvested), the others price indices; ^OMXSPI and OSEBX.OL are
  all-share indices, not blue-chip ones; holidays differ per exchange so "5 bars" can span slightly different calendar days.
  Live run into the scratchpad (not output/): all 59 screened rows now have a value (before: 23 blank).
