"""Tests for dipdash.forecast: volatility range forecast (not a direction or price-target model)."""
import json
import importlib.util
import sys

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from dipdash import forecast as fc


HAS_ARCH = importlib.util.find_spec("arch") is not None
PRIMARY_METHODS = ("garch_t_fhs", "ewma_fallback")        # without `arch` the primary entry is the documented EWMA fallback


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
        if name == "garch_t_fhs":                          # without `arch` this entry is the EWMA fallback, so say which one was tested
            assert d["method"] == ("garch_t_fhs" if HAS_ARCH else "ewma_fallback")
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
    assert d["method"] in PRIMARY_METHODS and d["lo"] < d["mid"] < d["hi"]
    assert 0.05 < d["vol_ann"] < 0.40 and d["n_obs"] == 750
    txt = fc.range_label(d)
    assert "Typical 21-day range" in txt and "not a price target" in txt and "%" in txt


def test_garch_method_is_used_when_arch_is_installed():
    pytest.importorskip("arch")
    d = fc.range_forecast(const_vol())
    assert d["method"] == "garch_t_fhs" and d["lo"] < d["mid"] < d["hi"]


def test_missing_arch_falls_back_to_ewma(monkeypatch):
    monkeypatch.setitem(sys.modules, "arch", None)             # makes `from arch import ...` raise ImportError
    d = fc.range_forecast(const_vol())
    assert d["method"] == "ewma_fallback" and d["reason"] is None and d["lo"] < 0 < d["hi"]
    g = fc.all_ranges(const_vol(), 21, seed=0)["garch_t_fhs"]
    assert g["method"] == "ewma_fallback" and g["fit_error"]


# ---------------------------------------------------------------- RES-4: frozen spec, register before computing
def _load_calibration_script():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_forecast_calibration.py"
    spec = importlib.util.spec_from_file_location("run_forecast_calibration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_frozen_forecast_criterion_equals_the_docstring_and_the_constants():
    mod = _load_calibration_script()
    doc = " ".join(fc.__doc__.split())
    assert mod.CRITERION_TEXT and mod.CRITERION_TEXT in doc and mod.CRITERION_TEXT.endswith("decision not to show the range.") and "relax it)." in mod.CRITERION_TEXT
    assert f"within {mod.TARGET:.2f} +/- {mod.TOL_ALL:.2f}" in mod.CRITERION_TEXT and f"within {mod.TARGET:.2f} +/- {mod.TOL_DIP:.2f}" in mod.CRITERION_TEXT
    assert "Two attempts in total" in mod.CRITERION_TEXT and mod.ATTEMPTS == (1, 2)
    assert f"<= {mod.TOL_ALL:.2f}" in mod.VERDICT_TEXT and f"<= {mod.TOL_DIP:.2f}" in mod.VERDICT_TEXT
    oos = pd.DataFrame({"origin": pd.to_datetime(["2020-03-02", "2022-05-02", "2023-01-02"]), "dip": [True, False, True],
                        "group": ["US", "Other", "US"]})
    assert tuple(mod.groups(oos)) == mod.GROUPS                                         # the registered cell count is the computed one
    assert mod.PLANNED_CELLS == len(mod.GROUPS) * len(mod.METHODS) * 2 * 2 == 120


def test_calibration_runner_registers_before_any_forecast_and_logs_the_planned_cells(tmp_path, monkeypatch):
    """Guard: move registration after build_origins in the script and this test fails."""
    import json
    from dipdash import registry
    from dipdash.cache import save_raw_prices
    mod = _load_calibration_script()
    rng = np.random.default_rng(5)
    bars = {f"S{k}": (make_close(rng.normal(0, 0.025, 1000)), None) for k in range(3)}
    raw = save_raw_prices(bars, "synthetic", tmp_path / "raw")
    root = tmp_path / "out"
    real, calls = fc.all_ranges, []

    def spy(close, horizon=21, *, seed=0):
        if not calls:
            reg = registry.read_registry(root)
            assert len(reg) == 1 and reg["kind"].iloc[0] == "forecast", "a forecast was computed before registration"
            assert (tmp_path / "run" / f"spec_{reg['spec_hash'].iloc[0]}.json").exists(), "a forecast was computed before the spec file existed"
        calls.append(1)
        return real(close, horizon, seed=seed)

    monkeypatch.setattr(fc, "all_ranges", spy)
    real_bo, bo_calls = mod.build_origins, []

    def bo_spy(reg, *a, **k):                                            # F1: build_origins is spied and needs the token
        r = registry.read_registry(root)
        assert len(r) == 1 and r["kind"].iloc[0] == "forecast", "build_origins called before registration"
        bo_calls.append(1)
        return real_bo(reg, *a, **k)

    monkeypatch.setattr(mod, "build_origins", bo_spy)
    real_rt = registry.record_trials

    def rt_spy(reg, rows_):                                              # F3: ledger before any result file
        run = tmp_path / "run"
        assert not (run / "results.csv").exists() and not (run / "origins.csv.gz").exists() and not (run / "report_forecast.md").exists()
        return real_rt(reg, rows_)

    monkeypatch.setattr(registry, "record_trials", rt_spy)
    assert mod.main(["--raw", str(raw), "--workers", "1", "--out-root", str(root), "--out", str(tmp_path / "run")]) == 0
    assert calls and bo_calls == [1]
    reg = registry.read_registry(root)
    assert reg["status"].tolist() == ["complete"]
    log = registry.read_trials(root)
    assert len(log) == int(reg["planned_cells"].iloc[0]) == mod.PLANNED_CELLS
    prim = log[log["primary"]]
    assert len(prim) == 4 and set(prim["group"]) == set(mod.VERDICT_GROUPS) and set(prim["stat"]) == {"coverage"}
    assert set(prim["cell"]) == {"garch_t_fhs|attempt1", "garch_t_fhs|attempt2"}
    spec = json.loads((tmp_path / "run" / "spec_forecast.json").read_text())
    assert spec["criterion_text"] == mod.CRITERION_TEXT and spec["spec_hash"] == registry.hash_for("forecast", spec)
    report = (tmp_path / "run" / "report_forecast.md").read_text(encoding="utf-8")
    assert "Out-of-sample period used before:" in report and spec["spec_hash"] in report


def test_build_origins_refuses_without_a_registration():
    from dipdash import registry
    mod = _load_calibration_script()
    with pytest.raises(registry.RegistrationError):
        mod.build_origins(None, {}, {}, 1)


def test_reuse_needs_matching_origins_meta_and_limit_is_refused_on_the_default_root(tmp_path, monkeypatch):
    from dipdash import registry
    from dipdash.cache import save_raw_prices
    mod = _load_calibration_script()
    rng = np.random.default_rng(5)
    raw = save_raw_prices({f"S{k}": (make_close(rng.normal(0, 0.025, 1000)), None) for k in range(2)}, "synthetic", tmp_path / "raw")
    args = ["--raw", str(raw), "--workers", "1", "--out-root", str(tmp_path / "out"), "--out", str(tmp_path / "run")]
    assert mod.main(args) == 0
    meta_p = tmp_path / "run" / mod.META_FILE
    meta = json.loads(meta_p.read_text())
    assert set(meta) == {"spec_hash", "raw_sha256", "limit", "cutoff"}
    n_before = len(registry.read_registry(tmp_path / "out"))
    assert mod.main(args + ["--reuse"]) == 0                                           # same spec: accepted
    meta_p.write_text(json.dumps({**meta, "spec_hash": "0" * 16}))
    assert mod.main(args + ["--reuse"]) == 2                                           # different spec hash: refused
    meta_p.unlink()
    assert mod.main(args + ["--reuse"]) == 2                                           # no meta: refused
    assert len(registry.read_registry(tmp_path / "out")) == n_before + 1               # refusals did not register anything
    assert mod.main(["--raw", str(raw), "--limit", "1", "--out", str(tmp_path / "x")]) == 2    # default root + --limit: refused
