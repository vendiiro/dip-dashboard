# Not verified: Amsterdam, Xetra, Paris, Swiss and Oslo prices

- Date: 2026-11-02
- Topic: data
- Origin: migrated, old entry 15 of 54 (text verbatim)

---

- 2026-11-02 (M2) NOT verified: Amsterdam, Xetra, Paris, Swiss and Oslo lines (ASML.AS, SAP.DE, SIE.DE, NESN.SW, ROG/NOVN, MC.PA, OR.PA, AIR.PA,
  EQNR.OL, DNB.OL) have no independent source reachable from the build environment (Stooq and SEC are blocked by the network policy; every other
  keyless source I tried was US-only or needs an API key). They get the internal checks only. Free keys (Alpha Vantage, Twelve Data) in `.env` would
  allow a check; not set up. Dividend adjustment is not verified for any ticker.
