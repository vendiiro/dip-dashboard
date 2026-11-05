"""Forecast calibration runner: shared dip state and split (RES-8). Synthetic data only; the model is stubbed."""
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dipdash import backtest as bt
from dipdash.config import Settings

S = Settings()


def load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_forecast_calibration.py"
    spec = importlib.util.spec_from_file_location("run_forecast_calibration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_ranges(close, horizon=21, *, seed=0):
    d = {"lo": -0.05, "mid": 0.0, "hi": 0.05, "vol_ann": 0.2, "method": "garch_t_fhs"}
    return {"garch_t_fhs": d, "ewma": dict(d, method="ewma"), "naive": dict(d, method="naive")}


def series(n=700, seed=1):
    r = np.random.default_rng(seed).normal(0, 0.02, n)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=pd.bdate_range("2018-01-01", periods=n))


def test_one_stock_looks_the_dip_up_by_origin_date(monkeypatch):
    mod = load_script()
    monkeypatch.setattr(mod.fc, "all_ranges", fake_ranges)
    close = series()
    dip = mod.origin_dips(close, S)
    rows = mod._one_stock(("X", close, dip))[1]
    assert rows and any(r["dip"] for r in rows) and not all(r["dip"] for r in rows)
    want = bt.signals(close, S)["dip"]
    for r in rows:
        assert r["dip"] == bool(want.loc[r["origin"]])
    assert {r["origin"] for r in rows} == {close.index[k] for k in range(mod.START, len(close) - mod.H, mod.STEP)}


def test_forecast_dip_state_includes_the_20d_rule():
    mod = load_script()
    from test_backtest import slow_slide
    c = slow_slide(n=500)
    d = mod.origin_dips(c, S)
    assert bool(d.iloc[-1]) is True and d.index.equals(c.index)
    sig = bt.signals(c, S)
    assert sig["r1"].iloc[-1] > -0.04 and sig["r5"].iloc[-1] > -0.07                 # only the 20-day rule fires


def test_every_origin_has_enough_history():
    mod = load_script()
    close = series(700)
    sig = bt.signals(close, S)
    assert sig["valid"].iloc[mod.START:].all()                                         # 252 bars needed, origins start at bar 400
    assert not sig["valid"].iloc[:251].any()
    mod.origin_dips(close, S)                                                          # does not raise
    with pytest.raises(AssertionError):
        mod.origin_dips(close.iloc[:300], S)                                           # a short series is refused, not silently False


def test_forecast_spec_text_matches_the_rule(tmp_path):
    mod = load_script()
    raw = tmp_path / "r.csv.gz"
    raw.write_bytes(b"x")
    s2 = replace(S, dip=replace(S.dip, drop_1d=0.05, drop_5d=0.08, drawdown_20d=0.15), backtest=replace(S.backtest, oos_fraction=0.3))
    spec = mod.forecast_spec(raw, ["A"], pd.Timestamp("2020-01-02"), 0, "f", s2)
    txt = spec["design"]["dip_state"]
    for part in ("1-day return <= -5%", "5-day return <= -8%", "15% below its 20-day high", "252"):
        assert part in txt, (part, txt)
    assert spec["split"]["oos_fraction"] == 0.3
    assert spec["design"]["dip_settings"] == {"drop_1d": 0.05, "drop_5d": 0.08, "drawdown_20d": 0.15}
    assert mod.forecast_spec(raw, ["A"], pd.Timestamp("2020-01-02"), 0, "f", S)["spec_hash"] != spec["spec_hash"]


def test_main_uses_shared_cutoff_and_refuses_an_old_cache(tmp_path, monkeypatch):
    from dipdash.cache import save_raw_prices
    from test_backtest_run import synthetic
    mod = load_script()
    prices, ix, uni, q, s = synthetic(n_stocks=3)
    bars = {t: (c, pd.Series(1000.0, index=c.index)) for t, c in prices.items()}
    raw = save_raw_prices(bars, "synthetic", tmp_path / "raw")
    monkeypatch.setattr(mod, "load_settings", lambda: s)
    monkeypatch.setattr(mod, "load_universe", lambda: uni)
    monkeypatch.setattr(mod.fc, "all_ranges", fake_ranges)
    monkeypatch.setattr(mod.fc, "range_forecast", lambda c, *a, **k: None)
    monkeypatch.setattr(mod, "chart", lambda *a, **k: None)
    root = tmp_path / "out"
    args = ["--raw", str(raw), "--out-root", str(root), "--out", str(root / "run"), "--workers", "1"]
    assert mod.main(args) == 0
    spec = json.loads((root / "run" / "spec_forecast.json").read_text())
    assert spec["split"]["cutoff"] == str(bt.shared_cutoff(prices, s).date())
    assert spec["split"]["oos_fraction"] == s.backtest.oos_fraction
    meta_p = root / "run" / mod.META_FILE
    old = json.loads(meta_p.read_text())
    meta_p.write_text(json.dumps({**old, "spec_hash": "0" * 16}))                      # an origins cache from the old definition
    assert mod.main(args + ["--reuse"]) == 2
