# Bug fixed: market-cap check converts to USD

- Date: 2026-11-02
- Topic: screen
- Origin: migrated, old entry 16 of 54 (text verbatim)

---

- 2026-11-02 (M2) BUG FOUND in the seed: the "market cap >= 20B" check compared the raw number in local currency (SEK, DKK, NOK, CHF, EUR) with 20B.
  It now converts to USD with Yahoo FX rates (`fx.py`); a missing currency or rate gives "no data", never a guess. Label is now "Market cap >= 20B USD".
  No stock in today's universe changes result; it matters once mid-caps are added. Rates are saved in the payload (`fx_to_usd`).
