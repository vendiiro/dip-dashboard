# Residual move against the stock's own index (descriptive only)

- Date: 2026-11-04
- Topic: screen
- Origin: migrated, old entry 50 of 54 (text verbatim)

---

- 2026-11-04 (residual move) New `src/dipdash/residual.py`, `residual_move(stock_close, index_close)` -> res1, res5, res5z, beta, beta_raw, beta_clipped, n_obs, asof, reason. Market model: the stock's 1d/5d move minus beta times
  the move of ITS OWN mapped index (`pick_index`). DESCRIPTIVE ONLY: it shows how much of a move the index does not explain; it was NOT backtested and nothing here says it predicts a rebound or anything else.
  Choices: (1) beta = OLS slope with intercept on the last 252 daily returns, EXCLUDING the most recent 5 returns (the very move being measured, so it cannot contaminate beta or residual volatility; a test inserts a -40% crash
  in those bars and beta is unchanged); at least 120 returns or the result is None with a reason (no guess). (2) Stock and index closes are inner-joined on common dates before returns are taken (a missing day on either side becomes
  a multi-day return on both); the index must have a bar on the stock's own last date, else None, so a stock bar one day behind is compared with the index move ending on ITS date and never with a later index bar.
  tz-aware Yahoo index stamps are made naive dates first. (3) No winsorizing (a large daily move is real information here; bad prints are validate.py's job). (4) beta clipped to [0, 3] for the residual, raw value kept: a negative beta
  for a blue chip is estimation noise, not a hedge, and clipping to 0 means "no market adjustment"; beta > 3 is implausible for these names and would over-subtract the index. (5) alpha not subtracted (daily alpha is below its own noise).
  (6) res5z = res5 / (residual daily sd * sqrt(5)); assumes uncorrelated daily residuals and ignores fat tails, so use it to rank, not as a p-value. Residual sd uses the clipped beta.
  Data: `fetch_indices(..., history=dict)` now also fills {symbol: ~2y closes} for the beta fit; the payload rows still carry only the 12 closes. The default Yahoo index fetch changed from 1mo to 2y. Nothing is written to data/.
  Caveats: betas are estimated from one year of one index (all-share/total-return index differences, see the market-context entry); a single event (earnings gap) in the window moves beta; the estimate is wide for a single stock
  (roughly +/-0.2 to 0.3 at 95% for typical stocks with 252 days); the market model leaves out sector and size effects.
  Real run 2026-11-04 (170 stocks): beta median 0.71, min -0.69 (COP), max 3.34 (MU); about 13 stocks had negative raw beta (telecoms, staples, energy, tobacco) and 3 exceeded 3 (MU, AMD, INTC) and were clipped.
