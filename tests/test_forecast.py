"""Tests for dipdash.forecast: volatility range forecast (not a direction or price-target model)."""
import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from dipdash import forecast as fc


def make_close(returns, start="2015-01-01"):
    idx = pd.bdate_range(start, periods=len(returns) + 1)
    return pd.Series(100 * np.exp(np.concatenate([[0.0], np.cumsum(returns)])), index=idx)


def const_vol(n=1000, sigma=0.01, seed=1):
    return make_close(np.random.default_rng(seed).normal(0, sigma, n))


def width(d):
    return np.log1p(d["hi"]) - np.log1p(d["lo"])


def test_constant_vol_range_matches_theory_for_all_methods():
    close = const_vol()
    theory = 2 * norm.ppf(0.9) * 0.01 * np.sqrt(21)
    for name, d in fc.all_ranges(close, 21, seed=0).items():
        assert d["reason"] is None, name
        assert width(d) == pytest.approx(theory, rel=0.25), name
        assert abs(np.log1p(d["mid"])) < 0.01, name        # neutral drift


def test_vol_after_shock_exceeds_calm_baseline():
    rng = np.random.default_rng(2)
    calm = rng.normal(0, 0.008, 900)
    shocked = np.concatenate([calm, [-0.05, 0.04, -0.045, 0.04]])
    a = fc.range_forecast(make_close(calm), seed=0)
    b = fc.range_forecast(make_close(shocked), seed=0)
    assert b["vol_ann"] > 1.08 * a["vol_ann"]
    assert b["hi"] - b["lo"] > a["hi"] - a["lo"]


def test_too_short_history_gives_none_and_reason():
    d = fc.range_forecast(const_vol(n=300))
    assert d["lo"] is None and d["mid"] is None and d["hi"] is None
    assert d["method"] is None and "400" in d["reason"] and d["n_obs"] == 300
    assert fc.range_label(d) == ""


def test_non_convergence_falls_back_to_ewma_and_is_flagged(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("optimizer failed")
    monkeypatch.setattr(fc, "_garch_fhs", boom)
    d = fc.range_forecast(const_vol())
    assert d["method"] == "ewma_fallback"
    assert d["reason"] is None and d["lo"] < 0 < d["hi"]


def test_never_looks_past_last_date():
    close = const_vol(n=1100)
    k = 1000
    changed = close.copy()
    changed.iloc[k + 1:] *= 5.0                               # wreck everything after k
    a = fc.range_forecast(close.iloc[: k + 1], seed=3)
    b = fc.range_forecast(changed.iloc[: k + 1], seed=3)
    assert a == b
    assert a["asof"] == close.index[k].date().isoformat()


def test_deterministic_with_seed_and_seed_matters_little():
    close = const_vol()
    assert fc.range_forecast(close, seed=5) == fc.range_forecast(close, seed=5)
    a, b = fc.range_forecast(close, seed=5), fc.range_forecast(close, seed=6)
    assert abs(a["hi"] - b["hi"]) < 0.01


def test_api_keys_and_fraction_units():
    d = fc.range_forecast(const_vol())
    assert set(d) == {"lo", "mid", "hi", "vol_ann", "method", "n_obs", "asof", "reason"}
    assert d["method"] == "garch_t_fhs" and d["lo"] < d["mid"] < d["hi"]
    assert 0.05 < d["vol_ann"] < 0.40 and d["n_obs"] == 750
    txt = fc.range_label(d)
    assert "Typical 21-day range" in txt and "not a price target" in txt and "%" in txt
