# Thresholds from settings.toml, universe from universe.csv; unknown keys are errors

- Date: 2026-11-02
- Topic: screen
- Origin: migrated, old entry 6 of 54 (text verbatim)

---

- 2026-11-02 (M1): Thresholds now come from `config/settings.toml`; the universe from `config/universe.csv`, which gained a hand-assigned
  `sector` column (approximate GICS-style groups, not an official feed). Unknown keys in settings are an error, so a typo cannot silently
  fall back to a default. `tests/test_config.py` checks that the code defaults equal the file.
