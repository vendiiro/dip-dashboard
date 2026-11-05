# Default view follows the CLAUDE.md dip rules

- Date: 2026-11-02
- Topic: dashboard
- Origin: migrated, old entry 22 of 54 (text verbatim)

---

- 2026-11-02 (M3) DEFAULT VIEW CHANGED from the demo: the demo defaulted to one window (5 days, -7%), which showed 3 dips on live data while the rule in
  CLAUDE.md (1-day <= -4% OR 5-day <= -7% OR >= 12% below the 20-day high) gives 11. The default is now "Default rules", driven by `settings.toml`
  (slider disabled, labelled "set in settings.toml"); the single-window options remain for exploring. A browser test ties the rows shown to the Python `dip`
  flag, and another uses one stock per rule, so a page that implements only one rule fails.
