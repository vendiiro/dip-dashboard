"""Feature experiment: causal features, planted effect found OOS, null not found, in-sample only fixes sign and cut points."""
import numpy as np
import pandas as pd

from dipdash.feature_experiment import (FAMILY, Settings, compute_features, demeaned_target, evaluate_features, freeze_spec,
                                        holm, mde, month_bootstrap, spearman, tercile_edges)


def series(n=420, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=idx)
    vol = pd.Series(rng.integers(1_000, 5_000, n).astype(float), index=idx)
    return close, vol


def test_features_known_values():
    close, vol = series()
    f = compute_features(close, vol)
    t = 300
    c, v = close.to_numpy(), vol.to_numpy()
    r = c[1:] / c[:-1] - 1                                    # r[k] is the return into bar k+1
    prior = r[t - 61:t - 1]                                   # returns into bars t-60 .. t-1
    assert np.isclose(f["f1_volume_ratio"].iloc[t], np.log(v[t] / np.median(v[t - 20:t])))
    assert np.isclose(f["f2_mom_12_1"].iloc[t], c[t - 21] / c[t - 252] - 1)
    assert np.isclose(f["f3_volscaled_drop"].iloc[t], r[t - 1] / prior.std(ddof=1))
    assert f["f4_days_since_high"].iloc[t] == np.argmax(c[t - 251:t + 1][::-1])
    assert np.isclose(f["f5_realised_vol"].iloc[t], prior.std(ddof=1) * np.sqrt(252))
    assert np.isclose(f["f6_dd_52w"].iloc[t], c[t] / c[t - 251:t + 1].max() - 1)


def test_features_use_only_data_up_to_t():
    close, vol = series()
    full = compute_features(close, vol)
    for t in (260, 300, 419):
        cut = compute_features(close.iloc[:t + 1], vol.iloc[:t + 1]).iloc[-1]
        assert np.allclose(cut.to_numpy(float), full.iloc[t].to_numpy(float), equal_nan=True)
    # garbage after t (a crash and a volume spike on t+1 onwards) must not move any feature at or before t
    t = 300
    c2, v2 = close.copy(), vol.copy()
    c2.iloc[t + 1:] *= 0.3
    v2.iloc[t + 1:] *= 50
    bent = compute_features(c2, v2)
    assert np.allclose(bent.iloc[:t + 1].to_numpy(float), full.iloc[:t + 1].to_numpy(float), equal_nan=True)
    # and a change AT t does move it (the test would otherwise be vacuous)
    c3 = close.copy()
    c3.iloc[t] *= 0.8
    assert not np.isclose(compute_features(c3, vol)["f6_dd_52w"].iloc[t], full["f6_dd_52w"].iloc[t])


def test_days_since_high_zero_at_new_high():
    idx = pd.bdate_range("2019-01-01", periods=300)
    close = pd.Series(np.linspace(50, 100, 300), index=idx)
    f = compute_features(close, None)
    assert f["f4_days_since_high"].iloc[-1] == 0 and f["f6_dd_52w"].iloc[-1] == 0
    assert f["f1_volume_ratio"].isna().all()


def test_demeaned_target_uses_all_stocks_same_day():
    days = pd.DataFrame({"date": pd.to_datetime(["2020-01-02"] * 3 + ["2020-01-03"] * 2), "fwd21": [0.1, 0.2, 0.3, 0.0, 0.2]})
    t = demeaned_target(days, 21)
    assert np.allclose(t, [-0.1, 0.0, 0.1, -0.1, 0.1])


def synth_events(rho_signal: float, seed=3, n_months=100, per=60):
    rng = np.random.default_rng(seed)
    months = pd.period_range("2012-01", periods=n_months, freq="M").astype(str)
    rows = []
    for m in months:
        x = rng.normal(size=per)
        noise = rng.normal(size=per)
        y = 0.02 * (rho_signal * x + np.sqrt(1 - rho_signal ** 2) * noise) + rng.normal(0, 0.002) * 0
        rows.append(pd.DataFrame({"month": m, "x": x, "target": y}))
    ev = pd.concat(rows, ignore_index=True)
    ev["period"] = np.where(ev["month"] <= months[59], "IS", "OOS")
    ev["group"] = np.where(np.arange(len(ev)) % 2 == 0, "US", "Europe+Nordic")
    rng2 = np.random.default_rng(seed + 1)
    for f in FAMILY:
        ev[f] = rng2.normal(size=len(ev))                    # null features
    ev["f2_mom_12_1"] = ev["x"]                              # planted
    return ev


def test_planted_effect_detected_and_nulls_not():
    ev = synth_events(0.15)
    res = evaluate_features(ev, Settings(draws=400, seed=5))
    fam = res[(res.stat == "spearman") & (res.period == "OOS") & (res.group == "All")].set_index("feature")
    assert fam.loc["f2_mom_12_1", "supported"]
    assert fam.loc["f2_mom_12_1", "lo"] > 0 and abs(fam.loc["f2_mom_12_1", "est"] - 0.15) < 0.06
    assert not fam.drop(index="f2_mom_12_1")["supported"].any()
    terc = res[(res.stat == "tercile_top_minus_bottom") & (res.group == "All") & (res.feature == "f2_mom_12_1")].iloc[0]
    assert terc["lo"] > 0


def test_sign_flip_between_periods_is_not_supported():
    ev = synth_events(0.15)
    isx = ev["period"] == "IS"
    ev.loc[isx, "target"] = -ev.loc[isx, "target"]          # in-sample sign opposite to the OOS effect
    fam = evaluate_features(ev, Settings(draws=300, seed=5))
    row = fam[(fam.feature == "f2_mom_12_1") & (fam.stat == "spearman") & (fam.period == "OOS") & (fam.group == "All")].iloc[0]
    assert row["sign_is"] == -1 and row["est"] > 0 and not row["supported"]


def test_in_sample_only_fixes_sign_and_cutpoints():
    ev = synth_events(0.15)
    base = evaluate_features(ev, Settings(draws=200, seed=5))
    ev2 = ev.copy()
    ev2.loc[ev2.period == "IS", "target"] *= 3                # scale in-sample targets: sign and ranks unchanged
    again = evaluate_features(ev2, Settings(draws=200, seed=5))
    a = base[base.period == "OOS"].reset_index(drop=True)
    b = again[again.period == "OOS"].reset_index(drop=True)
    assert np.allclose(a[["est", "lo", "hi"]].to_numpy(float), b[["est", "lo", "hi"]].to_numpy(float), equal_nan=True)
    x = np.arange(90.0)
    assert tercile_edges(x) == tercile_edges(np.concatenate([x, [1e9]])[:90])


def test_holm_mde_and_bootstrap_basics():
    rej, adj = holm([0.001, 0.02, 0.5, 0.6, 0.7, 0.8], alpha=0.10)
    assert rej[0] and not rej[2] and adj[0] == 0.006
    assert np.isclose(mde(-0.05, 0.05, 0.90), (1.6449 + 0.8416) * 0.1 / (2 * 1.6449), rtol=1e-3)
    rng = np.random.default_rng(1)
    x = rng.normal(size=600)
    r = month_bootstrap(spearman, [x, x + rng.normal(size=600)], np.repeat(np.arange(30), 20), 300, 0.9, 1)
    assert r["lo"] < r["est"] < r["hi"] and r["n_months"] == 30 and r["p"] < 0.05


def test_spec_hash_ignores_notes_only():
    a = freeze_spec({"x": 1}, "2020-02-10", 171, "features_t", {"draws": 5})
    b = freeze_spec({"x": 1}, "2020-02-10", 171, "features_t", {"draws": 5})
    c = freeze_spec({"x": 1}, "2020-02-11", 171, "features_t", {"draws": 5})
    assert a["spec_hash"] == b["spec_hash"] != c["spec_hash"]
