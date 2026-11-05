import tomllib
from pathlib import Path

import pytest

from dipdash.config import Settings, load_settings, load_universe


def test_real_settings_file_loads_with_expected_values():
    s = load_settings()
    assert s.dip.drop_1d == 0.04 and s.dip.drop_5d == 0.07 and s.dip.drawdown_20d == 0.12
    assert s.quality.market_cap_min == 20_000_000_000
    assert s.backtest.horizons == (5, 21, 63)
    assert s.data.max_stale_trading_days == 4


def test_code_defaults_match_the_settings_file():
    assert Settings() == load_settings()


def test_run_health_thresholds_in_toml_equal_dataclass_defaults():
    from dipdash.config import DataSettings
    raw = tomllib.loads((Path(__file__).resolve().parents[1] / "config" / "settings.toml").read_text(encoding="utf-8"))["data"]
    d = DataSettings()
    for k in ("min_fundamentals_share", "min_bars_share", "min_earnings_share"):
        assert k in raw, k
        assert raw[k] == getattr(d, k) == getattr(load_settings().data, k)
    assert (d.min_fundamentals_share, d.min_bars_share, d.min_earnings_share) == (0.8, 0.8, 0.5)


def test_run_health_thresholds_do_not_change_the_backtest_spec_hash():
    import dataclasses
    from datetime import date
    import pandas as pd
    from dipdash.backtest_run import freeze_spec
    base = Settings()
    other = dataclasses.replace(base, data=dataclasses.replace(base.data, min_fundamentals_share=0.1, min_bars_share=0.1, min_earnings_share=0.1))
    cal = pd.bdate_range("2015-01-01", "2024-12-31")
    a = freeze_spec(base, [], {}, cal)
    b = freeze_spec(other, [], {}, cal)
    assert a == b


def test_partial_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("[dip]\ndrop_1d = 0.03\n")
    s = load_settings(p)
    assert s.dip.drop_1d == 0.03 and s.dip.drop_5d == 0.07 and s.quality == Settings().quality


def test_typo_in_a_key_is_an_error_not_a_silent_default(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("[dip]\ndrop_1_day = 0.03\n")
    with pytest.raises(ValueError, match="drop_1_day"):
        load_settings(p)


def test_unknown_section_is_an_error(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("[dips]\ndrop_1d = 0.03\n")
    with pytest.raises(ValueError, match="dips"):
        load_settings(p)


def test_real_universe_is_clean():
    u = load_universe()
    assert len(u) >= 60
    assert len({s.ticker for s in u}) == len(u)
    assert {s.region for s in u} == {"US", "Europe", "Nordic"}
    assert all(s.sector for s in u)


def test_universe_with_only_tickers_gets_defaults(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text("ticker\nAAA\nBBB\n")
    u = load_universe(p)
    assert [(s.ticker, s.name, s.region, s.sector) for s in u] == [("AAA", "AAA", "Other", ""), ("BBB", "BBB", "Other", "")]


def test_universe_rejects_duplicates_empty_tickers_and_missing_column(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text("ticker,name\nAAA,a\nAAA,b\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_universe(p)
    p.write_text("ticker,name\n,a\n")
    with pytest.raises(ValueError, match="empty ticker"):
        load_universe(p)
    p.write_text("symbol,name\nAAA,a\n")
    with pytest.raises(ValueError, match="ticker"):
        load_universe(p)


def test_indices_come_from_the_file_and_match_the_defaults():
    from dipdash.config import DEFAULT_INDICES
    s = load_settings()
    assert [(i.symbol, i.region) for i in s.indices] == [("^GSPC", "US"), ("^STOXX", "Europe"), ("^OMXH25", "Nordic")]
    assert s.indices == DEFAULT_INDICES


def test_a_file_without_indices_uses_the_defaults_and_a_typo_is_an_error(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text("[dip]\ndrop_1d = 0.03\n")
    assert load_settings(p).indices == Settings().indices
    p.write_text('[[indices]]\nsymbol = "^X"\nname = "X"\nregoin = "US"\n')
    with pytest.raises(ValueError, match="regoin"):
        load_settings(p)
    p.write_text('[[indices]]\nsymbol = "^X"\nname = "X"\nregion = "US"\n')
    assert [i.symbol for i in load_settings(p).indices] == ["^X"]


def test_unknown_check_key_fails_at_load(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text('[quality.not_applicable]\nfinancials = ["debtToEquity", "freeCashFlow"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="freeCashFlow"):
        load_settings(p)


def test_sector_rules_load_as_tuples_and_floats(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text('[quality.not_applicable]\nbanks = ["debtToEquity"]\n[quality.debt_to_equity_max_by_sector]\n"real estate" = 400\n',
                 encoding="utf-8")
    q = load_settings(p).quality
    assert q.not_applicable == {"banks": ("debtToEquity",)} and q.debt_to_equity_max_by_sector == {"real estate": 400.0}
