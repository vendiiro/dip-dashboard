import os
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dipdash.backtest import (EU, US, Cell, add_events, date_shift_placebo, add_peer_returns, add_periods, apply_cooldown, build_days,
                              cell_events, cluster_bootstrap, forward, group_of, own_baseline, placebo_means,
                              signals, split_cutoff, stress_flags, summarize)
from dipdash.config import Settings, Stock
from dipdash.metrics import compute_metrics
from dipdash.screen import dip_reasons, is_falling_knife
from synth import dates, geometric

S = Settings()


def walk(seed, n, sigma=0.02, drift=0.0, start=100.0, end="2026-10-29"):
    r = np.random.default_rng(seed).normal(drift, sigma, n)
    return pd.Series(start * np.exp(np.cumsum(r)), index=dates(n, end))


# ======================================================================== signals
def rise_then_fall(seed, up=450, down=250, sigma=0.02):
    r = np.concatenate([np.random.default_rng(seed).normal(0.002, sigma, up), np.random.default_rng(seed + 1).normal(-0.006, sigma, down)])
    return pd.Series(100 * np.exp(np.cumsum(r)), index=dates(up + down))


@pytest.mark.parametrize("seed, kind", [(1, "volatile"), (2, "rise_then_fall")])
def test_vectorised_signals_equal_the_dashboard_logic_bar_by_bar(seed, kind):
    """The backtest must test the rule the dashboard actually applies (metrics.py + screen.py)."""
    c = walk(seed, 700, 0.03) if kind == "volatile" else rise_then_fall(seed)
    drift = 0.0 if kind == "volatile" else -1
    full = signals(c, S)
    seen = {"dip": set(), "knife": set()}
    for k in range(280, 700, 5):
        m = compute_metrics(c.iloc[:k + 1], None)
        want_dip = bool(dip_reasons(m, S.dip))
        want_knife = is_falling_knife(m, S.falling_knife)
        row = full.iloc[k]
        assert bool(row["dip"]) == want_dip, (k, m)
        assert bool(row["knife"]) == want_knife, (k, m)
        seen["dip"].add(want_dip); seen["knife"].add(want_knife)
    assert seen["dip"] == {True, False}                      # the test exercised both outcomes
    if kind == "rise_then_fall":
        assert seen["knife"] == {True, False}


def test_signals_are_causal_a_prefix_gives_the_same_flags():
    c = walk(3, 600, 0.03)
    full = signals(c, S)
    for k in range(260, 600, 11):
        pre = signals(c.iloc[:k + 1], S).iloc[-1]
        for col in ("f1", "f5", "f20", "dip", "knife"):
            assert bool(pre[col]) == bool(full.iloc[k][col]), (k, col)


def test_changing_the_future_cannot_change_todays_signal():
    c = walk(4, 500, 0.03)
    base = signals(c, S)
    k = 400
    shocked = c.copy()
    shocked.iloc[k + 1:] = shocked.iloc[k + 1:] * 0.3        # a crash after bar k
    after = signals(shocked, S)
    assert (base.iloc[:k + 1][["dip", "knife"]].to_numpy() == after.iloc[:k + 1][["dip", "knife"]].to_numpy()).all()


def test_no_signal_without_a_full_year_of_history():
    c = walk(5, 600, 0.04)
    sig = signals(c, S)
    assert not sig["dip"].iloc[:251].any() and not sig["knife"].iloc[:251].any()


def test_each_rule_flags_at_its_limit():
    c = geometric(300, 0.0005)
    c.iloc[-1] = c.iloc[-2] * 0.96                           # exactly -4% in one day
    row = signals(c, S).iloc[-1]
    assert row["f1"] and row["dip"]
    c.iloc[-1] = c.iloc[-2] * 0.9601
    assert not signals(c, S).iloc[-1]["f1"]


# ======================================================================== cooldown
def test_cooldown_counts_from_the_last_kept_signal():
    flag = np.zeros(60, dtype=bool)
    flag[[0, 1, 2, 21, 22, 23, 44]] = True
    assert list(np.flatnonzero(apply_cooldown(flag, 21))) == [0, 22, 44]          # bar 21 is exactly 21 after bar 0: still inside the window
    assert list(np.flatnonzero(apply_cooldown(flag, 0))) == [0, 1, 2, 21, 22, 23, 44]
    assert apply_cooldown(np.zeros(5, dtype=bool), 21).sum() == 0


def test_a_suppressed_signal_does_not_extend_the_cooldown():
    flag = np.zeros(60, dtype=bool)
    flag[[0, 20, 40]] = True          # 20 is inside the window of 0 and suppressed; 40 is 40 bars after 0, so kept
    assert list(np.flatnonzero(apply_cooldown(flag, 21))) == [0, 40]


# ======================================================================== forward returns
def test_entry_is_the_next_close_and_exit_h_bars_later():
    c = geometric(100, 0.01)
    f = forward(c, (5,))
    assert f["fwd5"].iloc[10] == pytest.approx(1.01 ** 5 - 1)             # same for every bar of a constant-growth path
    assert f["entry_date"].iloc[10] == c.index[11] and f["exit5"].iloc[10] == c.index[16]
    assert f["fwd5"].iloc[10] == pytest.approx(c.iloc[16] / c.iloc[11] - 1)   # not c[15]/c[10]: no look at the signal bar's own price


def test_returns_are_missing_when_the_window_runs_past_the_data():
    f = forward(geometric(30, 0.01), (5,))
    assert f["fwd5"].iloc[-6:].isna().all() and f["fwd5"].iloc[-7:-6].notna().all()
    assert f["exit5"].iloc[-6:].isna().all()


def test_max_adverse_move_is_the_worst_close_after_entry():
    v = [100.0] * 20
    v[10:16] = [100, 100, 90, 95, 120, 110]                   # entry at bar 11 (=100); worst close afterwards is 90
    c = pd.Series(v, index=dates(20))
    f = forward(c, (4,))
    assert f["mae4"].iloc[10] == pytest.approx(-0.10)
    assert f["fwd4"].iloc[10] == pytest.approx(110 / 100 - 1)          # exit at bar 15 (entry bar 11 + 4)
    rising = forward(geometric(30, 0.01), (5,))
    assert (rising["mae5"].dropna() == 0).all()               # never below entry -> 0, not positive


def test_signal_bar_move_is_not_part_of_the_return():
    v = [100.0] * 30
    v[11:] = [150.0] * 19                                     # a level shift ON the day after the signal bar (bar 10)
    f = forward(pd.Series(v, index=dates(30)), (5,))
    assert f["fwd5"].iloc[10] == pytest.approx(0.0)           # entry is the close of bar 11, after the shift: nothing to gain
    assert f["fwd5"].iloc[9] == pytest.approx(0.5)            # a signal one bar earlier enters at 100 and does see it


# ======================================================================== stress and split
def test_stress_flags_use_only_past_data_and_the_drawdown_limit():
    c = geometric(100, 0.0)
    c.iloc[70:] = 85.0                                        # 15% below the 60-bar high
    s = stress_flags(c, 60, 0.10)
    assert not s.iloc[:60].any() and s.iloc[70:].all() and not s.iloc[60:70].any()
    c.iloc[70:] = 91.0
    assert not stress_flags(c, 60, 0.10).iloc[70:].any()      # only 9% down


def test_split_cutoff_keeps_the_first_sixty_percent_in_sample():
    d = pd.bdate_range("2020-01-01", periods=100)
    cut = split_cutoff(d, 0.4)
    assert cut == d[59] and (d <= cut).sum() == 60
    assert split_cutoff(list(d) * 3, 0.4) == cut              # duplicates across stocks do not matter


def test_periods_purge_in_sample_signals_whose_window_crosses_the_cutoff():
    d = pd.bdate_range("2020-01-01", periods=100)
    c = pd.Series(100.0 + np.arange(100) * 0.1, index=d)
    days = build_days({"A": c}, [Stock("A", "A", "US")], {US: c, EU: c}, replace(S, backtest=replace(S.backtest, start_date="2020-01-01", horizons=(5,))))
    days, cutoff = add_periods(days, replace(S, backtest=replace(S.backtest, horizons=(5,))))
    assert cutoff == d[59]
    p = days.set_index("date")["period5"]
    assert p[d[53]] == "IS" and p[d[54]] == "purged" and p[d[59]] == "purged"     # exit = entry+5 = bar 54+... crosses bar 59 from bar 54 on
    assert p[d[60]] == "OOS" and p[d[99]] == "OOS"
    # bar 53: entry 54, exit 59 -> on the cutoff, allowed; bar 54: exit 60 -> after the cutoff, purged


# ======================================================================== bootstrap
def test_bootstrap_mean_interval_and_determinism():
    rng = np.random.default_rng(0)
    x = rng.normal(0.02, 0.05, 600)
    cl = np.repeat(np.arange(60), 10)
    m, lo, hi, n = cluster_bootstrap(x, cl, 2000, 0.90, 7)
    assert m == pytest.approx(x.mean()) and lo < m < hi and n == 60
    assert cluster_bootstrap(x, cl, 2000, 0.90, 7) == (m, lo, hi, n)           # same seed, same answer
    assert cluster_bootstrap(x, cl, 2000, 0.90, 8)[1] != lo                    # different seed, different draws


def test_clustered_interval_is_wider_than_a_naive_one_when_events_bunch_together():
    rng = np.random.default_rng(1)
    month_effect = np.repeat(rng.normal(0, 0.05, 50), 20)                       # whole months move together
    x = month_effect + rng.normal(0, 0.01, 1000)
    clustered = cluster_bootstrap(x, np.repeat(np.arange(50), 20), 2000, 0.90, 3)
    naive = cluster_bootstrap(x, np.arange(1000), 2000, 0.90, 3)
    assert (clustered[2] - clustered[1]) > 3 * (naive[2] - naive[1])


def test_bootstrap_interval_covers_the_true_mean_about_nine_times_in_ten():
    hits = 0
    for seed in range(60):
        rng = np.random.default_rng(100 + seed)
        x = rng.normal(0.01, 0.04, 300)
        _, lo, hi, _ = cluster_bootstrap(x, np.repeat(np.arange(30), 10), 500, 0.90, seed)
        hits += lo <= 0.01 <= hi
    assert 48 <= hits <= 60            # 90% nominal; loose bounds keep the test stable


def test_bootstrap_edge_cases():
    assert cluster_bootstrap(np.array([]), np.array([]), 100, 0.9, 1)[3] == 0
    m, lo, hi, n = cluster_bootstrap(np.array([1.0, 2.0, np.nan]), np.array(["a", "a", "b"]), 100, 0.9, 1)
    assert m == 1.5 and n == 1 and np.isnan(lo) and np.isnan(hi)               # NaNs dropped; one cluster gives no interval


# ======================================================================== placebo
def test_placebo_draws_only_from_the_pool_and_prefers_the_same_year():
    ev = pd.DataFrame({"ticker": ["A", "A"], "year": [2015, 2016], "fwd5": [0.10, 0.10]})
    pool = pd.DataFrame({"ticker": ["A"] * 4, "year": [2015, 2015, 2016, 2017], "fwd5": [0.01, 0.01, 0.03, 0.99]})
    dist, obs, n = placebo_means(ev, pool, "fwd5", 200, 1)
    assert n == 2 and obs == pytest.approx(0.10)
    assert np.allclose(dist, 0.02)                                              # (0.01 + 0.03) / 2 every time: never the 2017 value
    # no pool for the event's year: falls back to any year of the same stock
    ev2 = pd.DataFrame({"ticker": ["A"], "year": [2030], "fwd5": [0.1]})
    d2, _, n2 = placebo_means(ev2, pool, "fwd5", 500, 1)
    assert n2 == 1 and set(np.round(d2, 2)) <= {0.01, 0.03, 0.99}


def test_placebo_skips_events_without_a_pool_or_a_return():
    ev = pd.DataFrame({"ticker": ["A", "B", "A"], "year": [2015, 2015, 2015], "fwd5": [0.1, 0.1, np.nan]})
    pool = pd.DataFrame({"ticker": ["A"], "year": [2015], "fwd5": [0.0]})
    dist, obs, n = placebo_means(ev, pool, "fwd5", 50, 1)
    assert n == 1 and obs == pytest.approx(0.1)
    assert placebo_means(ev.iloc[1:2], pool, "fwd5", 50, 1)[2] == 0


# ======================================================================== cell arithmetic on a hand-built table
def mini(settings=None):
    s = settings or replace(S, backtest=replace(S.backtest, horizons=(5,), bootstrap_draws=300, placebo_draws=300))
    rows = []
    for t, grp in (("A", US), ("B", EU)):
        for i in range(10):
            rows.append({"ticker": t, "group": grp, "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i), "month": "2020-01", "year": 2020,
                         "dip": i in (2, 5), "knife": i == 5, "q": 80.0 if t == "A" else 40.0, "stress": i == 5,
                         "fwd5": 0.01 * (i + 1) if t == "A" else -0.01, "mae5": -0.02, "idx5": 0.005, "ew5": 0.0,
                         "suspect5": False, "period5": "OOS", "valid": True})
    d = pd.DataFrame(rows)
    d["tstart"] = np.where(d["ticker"] == "A", 0, 10)           # rows 0-9 are stock A, rows 10-19 stock B
    d["tend"] = np.where(d["ticker"] == "A", 10, 20)
    d["ev_V1_price_only"] = d["dip"]
    d["ev_V2_no_knife"] = d["dip"] & ~d["knife"]
    d["ev_V3_quality_indicative"] = d["dip"] & (d["q"] >= 60)
    return d, s


def test_cell_selection_by_variant_group_and_period():
    d, s = mini()
    assert len(cell_events(d, Cell("V1_price_only", 5, "All", "ALL"))) == 4
    assert len(cell_events(d, Cell("V2_no_knife", 5, "All", "ALL"))) == 2
    assert len(cell_events(d, Cell("V3_quality_indicative", 5, "All", "ALL"))) == 2           # only stock A has q >= 60
    assert len(cell_events(d, Cell("V1_price_only", 5, US, "ALL"))) == 2
    assert len(cell_events(d, Cell("V1_price_only", 5, "All", "OOS_exstress"))) == 2          # the stress day is dropped
    assert len(cell_events(d, Cell("V1_price_only", 5, "All", "IS"))) == 0


def test_baseline_is_the_stocks_own_mean_on_non_dip_days_only():
    d, _ = mini()
    base = own_baseline(d, Cell("V1_price_only", 5, "All", "ALL"))
    non_dip_a = [0.01 * (i + 1) for i in range(10) if i not in (2, 5)]
    assert base["A"] == pytest.approx(np.mean(non_dip_a)) and base["B"] == pytest.approx(-0.01)


def test_summary_numbers_match_hand_calculation():
    d, s = mini()
    r = summarize(d, Cell("V1_price_only", 5, "All", "ALL"), s)
    fwd = np.array([0.03, 0.06, -0.01, -0.01])                 # stock A days 2 and 5, stock B days 2 and 5
    c = s.backtest.cost_roundtrip
    assert r["n"] == 4 and r["n_stocks"] == 2 and r["n_dates"] == 2 and r["n_months"] == 1
    assert r["gross_mean"] == pytest.approx(fwd.mean())
    assert r["net_mean_1x"] == pytest.approx(fwd.mean() - c)
    assert r["net_mean_2x"] == pytest.approx(fwd.mean() - 2 * c) and r["net_mean_4x"] == pytest.approx(fwd.mean() - 4 * c)
    assert r["hit_rate"] == pytest.approx(0.5) and r["worst"] == pytest.approx(-0.01 - c)
    assert r["mae_median"] == pytest.approx(-0.02) and r["mae_worst"] == pytest.approx(-0.02)
    base_a = np.mean([0.01 * (i + 1) for i in range(10) if i not in (2, 5)])
    assert r["ex_own"] == pytest.approx(np.mean([0.03 - base_a, 0.06 - base_a, -0.01 + 0.01, -0.01 + 0.01]))
    assert r["ex_index"] == pytest.approx(fwd.mean() - 0.005) and r["ex_peers"] == pytest.approx(fwd.mean())
    assert r["n_suspect"] == 0


def test_an_empty_cell_returns_just_its_labels():
    d, s = mini()
    r = summarize(d, Cell("V1_price_only", 5, "All", "IS"), s)
    assert r["n"] == 0 and "gross_mean" not in r


def test_events_touching_a_suspect_jump_are_reported_separately():
    d, s = mini()
    d.loc[(d.ticker == "A") & d.dip, "suspect5"] = True
    r = summarize(d, Cell("V1_price_only", 5, "All", "ALL"), s)
    assert r["n_suspect"] == 2 and "ex_own_nosuspect" in r and r["n"] == 4        # still in the main numbers, plus a sensitivity


def test_peer_return_excludes_the_stock_itself():
    d = pd.DataFrame({"date": pd.to_datetime(["2020-01-01"] * 3 + ["2020-01-02"]), "fwd5": [0.1, 0.2, 0.6, 0.5]})
    out = add_peer_returns(d, (5,))
    assert out["ew5"].iloc[0] == pytest.approx(0.4) and out["ew5"].iloc[1] == pytest.approx(0.35) and out["ew5"].iloc[2] == pytest.approx(0.15)
    assert np.isnan(out["ew5"].iloc[3])                       # alone on its date: no peers


def test_group_mapping():
    assert group_of("US") == US and group_of("Europe") == EU and group_of("Nordic") == EU


# ======================================================================== end to end on synthetic universes
def universe(seed, n_stocks=18, n=1400, effect=0.0, jump=0.0):
    """Random-walk stocks. effect: extra daily log-return on bars i+2..i+6 after each dip event bar i (a real post-entry bounce).
    jump: extra log-return on bar i+1 only, i.e. BEFORE the next-close entry (must not show up in the results)."""
    rng = np.random.default_rng(seed)
    idx = dates(n, "2026-10-29")
    base_s = replace(S, backtest=replace(S.backtest, start_date="2000-01-01"))
    prices, uni = {}, []
    for k in range(n_stocks):
        r = rng.normal(0.0003, 0.016, n)
        close = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        if effect or jump:
            sig = signals(close, base_s)["dip"].to_numpy()
            for i in np.flatnonzero(apply_cooldown(sig, 21)):
                if i + 7 < n:
                    r[i + 1] += jump
                    r[i + 2:i + 7] += effect
            close = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        t = f"S{k}"
        prices[t] = close
        uni.append(Stock(t, t, "US" if k % 2 == 0 else "Europe"))
    ix = {US: pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), index=idx),
          EU: pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), index=idx)}
    s = replace(S, backtest=replace(S.backtest, start_date=str(idx[300].date()), horizons=(5, 21), bootstrap_draws=600, placebo_draws=400))
    days = build_days(prices, uni, ix, s)
    days = add_peer_returns(add_events(days, s), s.backtest.horizons)
    days, _ = add_periods(days, s)
    return days, s


def run(days, s, h=21, period="ALL"):
    return summarize(days, Cell("V1_price_only", h, "All", period), s)


def test_a_planted_post_entry_bounce_is_detected_and_a_null_universe_is_not():
    d1, s = universe(11, effect=0.006)
    r = run(d1, s)
    assert r["n"] > 150 and r["ex_own"] > 0.015 and r["ex_own_lo"] > 0 and r["placebo_p"] < 0.05
    assert r["ex_index"] > 0.01 and r["ex_peers"] > 0.01
    d0, s0 = universe(11)
    r0 = run(d0, s0)
    assert r0["ex_own_lo"] < 0 < r0["ex_own_hi"]


def test_false_positives_stay_near_the_nominal_rate_on_null_universes():
    excl = 0
    for seed in range(20, 28):
        d, s = universe(seed, n_stocks=12, n=1100)
        r = run(d, s)
        excl += not (r["ex_own_lo"] <= 0 <= r["ex_own_hi"])
    assert excl <= 2                   # nominal 10% of 8 is about 1


def test_a_jump_before_the_entry_bar_does_not_leak_into_the_result():
    d, s = universe(12, jump=0.10)
    ev = d[d["ev_V1_price_only"]]
    day_after = ev["close"].to_numpy()                          # not used; the check is on the forward return itself
    r = run(d, s, h=5)
    assert r["n"] > 200
    assert abs(r["gross_mean"]) < 0.02                          # a +10% move on bar i+1 is NOT in the return from the close of bar i+1
    # sanity: the jump really is in the data (a signal-bar-close entry would have captured it)
    d2 = d.sort_values(["ticker", "date"])
    nxt = d2.groupby("ticker")["close"].shift(-1) / d2["close"] - 1
    assert nxt[d2["ev_V1_price_only"]].mean() > 0.07


def test_out_of_sample_events_all_follow_the_cutoff_and_in_sample_windows_end_before_it():
    d, s = universe(13)
    cutoff = split_cutoff(d["date"].unique(), s.backtest.oos_fraction)
    for h in s.backtest.horizons:
        oos = d[d[f"period{h}"] == "OOS"]
        ins = d[d[f"period{h}"] == "IS"]
        assert (oos["date"] > cutoff).all()
        assert (ins["date"] <= cutoff).all() and (ins[f"exit{h}"] <= cutoff).all()
    assert (d["period21"] == "purged").sum() > 0


def test_placebo_pool_contains_only_non_dip_days():
    d, s = mini()
    d.loc[~d["dip"], "fwd5"] = 0.0           # every non-dip day returns exactly 0
    d.loc[d["dip"], "fwd5"] = 0.50           # every dip day returns +50%
    r = summarize(d, Cell("V1_price_only", 5, "All", "ALL"), s)
    assert r["placebo_obs"] == pytest.approx(0.50) and r["placebo_mean"] == pytest.approx(0.0)
    assert r["placebo_p"] < 0.05


def test_index_with_exchange_local_timestamps_still_lines_up_with_stocks():
    c = walk(30, 700, 0.02)
    ix = c.copy()
    ix.index = ix.index.tz_localize("America/New_York") + pd.Timedelta(hours=16)       # what Yahoo returns for an index
    s = replace(S, backtest=replace(S.backtest, start_date=str(c.index[300].date()), horizons=(5,)))
    a = build_days({"A": c}, [Stock("A", "A", "US")], {US: ix, EU: ix}, s)
    b = build_days({"A": c}, [Stock("A", "A", "US")], {US: c, EU: c}, s)
    assert a["idx5"].iloc[:-6].notna().all() and a["idx5"].iloc[-6:].isna().all()       # entry is 1 bar later, so the last 1 + 5 bars have no 5-day return
    assert np.allclose(a["idx5"], b["idx5"], equal_nan=True)


# ======================================================================== baseline hygiene and the new diagnostics
def test_baseline_ignores_days_where_no_signal_could_be_computed():
    d, _ = mini()
    d.loc[(d.ticker == "A") & (d.date <= pd.Timestamp("2020-01-02")), ["valid", "fwd5"]] = [False, 9.99]      # first two rows: history too short
    base = own_baseline(d, Cell("V1_price_only", 5, "All", "ALL"))
    assert base["A"] == pytest.approx(np.mean([0.01 * (i + 1) for i in (3, 4, 6, 7, 8, 9)]))        # the 9.99 rows are not in the baseline


def test_baseline_hit_rate_index_gap_and_stress_share_match_hand_calculation():
    d, s = mini()
    r = summarize(d, Cell("V1_price_only", 5, "All", "ALL"), s)
    nd = d[~d["dip"]]
    assert r["base_n"] == 16 and r["base_hit"] == pytest.approx(((nd["fwd5"] - s.backtest.cost_roundtrip) > 0).mean()) == pytest.approx(0.5)
    assert r["nd_vs_idx"] == pytest.approx((nd["fwd5"] - 0.005).mean())
    assert r["ev_stress_share"] == pytest.approx(0.5)


def test_date_shift_placebo_on_known_arrays():
    n = 600
    F = np.full(n, 0.01)                                        # one stock, every day returns +1%
    rows = np.arange(100, 300, 5)                               # 40 events
    z, full = np.zeros(len(rows), int), np.full(len(rows), n)
    flat = date_shift_placebo(rows, np.full(len(rows), 0.01), z, full, F, 400, 1)
    assert flat["shift_p"] > 0.9 and flat["shift_excess"] == pytest.approx(0.0)           # events no better than any other day
    better = date_shift_placebo(rows, np.full(len(rows), 0.5), z, full, F, 400, 1)
    assert better["shift_draws"] > 100                                                    # draws with too few matched events are dropped, not guessed
    assert better["shift_p"] == pytest.approx(1 / (better["shift_draws"] + 1)) and better["shift_excess"] == pytest.approx(0.49)


def test_date_shift_placebo_reads_the_shifted_row_of_the_right_stock():
    n = 300
    F = np.arange(n, dtype=float)                               # the value at row r is r, so a wrong row shows up immediately
    rows = np.arange(10, 50)                                    # 40 events
    res = date_shift_placebo(rows, np.zeros(40), np.zeros(40, int), np.full(40, n), F, 300, 2, lo=70, hi=100)
    # only positive lags stay inside rows 0..299, and they add 70..100 to each row: placebo mean - events' mean (0 here) = mean(rows) + lag
    assert res["shift_draws"] > 50
    assert 29.5 + 70 <= res["shift_mean"] <= 29.5 + 100
    # a stock that occupies only rows 0-49 (tend=50): no row shifted by 70 or more is inside it, so nothing is compared
    assert date_shift_placebo(rows, np.zeros(40), np.zeros(40, int), np.full(40, 50), F, 200, 2, lo=70, hi=100) == {}


def common_factor_universe(seed, n_stocks=12, n=1100, share=0.85):
    """Stocks that mostly move together (a shared market factor) and have no dip effect at all."""
    rng = np.random.default_rng(seed)
    idx = dates(n, "2026-10-29")
    f = rng.normal(0.0003, 0.016, n)
    prices, uni = {}, []
    for k in range(n_stocks):
        r = np.sqrt(share) * f + np.sqrt(1 - share) * rng.normal(0.0003, 0.016, n)
        prices[f"S{k}"] = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        uni.append(Stock(f"S{k}", f"S{k}", "US" if k % 2 == 0 else "Europe"))
    ix = {US: pd.Series(100 * np.exp(np.cumsum(f)), index=idx), EU: pd.Series(100 * np.exp(np.cumsum(f)), index=idx)}
    s = replace(S, backtest=replace(S.backtest, start_date=str(idx[300].date()), horizons=(21,), bootstrap_draws=400, placebo_draws=400))
    days = build_days(prices, uni, ix, s)
    days = add_peer_returns(add_events(days, s), s.backtest.horizons)
    days, _ = add_periods(days, s)
    return days, s


def test_independent_placebo_is_too_optimistic_when_events_share_dates_and_the_date_shift_is_not():
    """With a strong shared market factor and NO dip effect, random independent days reject far too often; shifting all events together does not."""
    indep = shift = 0
    runs = 10
    for seed in range(40, 40 + runs):
        d, s = common_factor_universe(seed)
        r = summarize(d, Cell("V1_price_only", 21, "All", "ALL"), s)
        indep += r["placebo_p"] < 0.05
        shift += r["shift_p"] < 0.05
    assert indep >= 3 * max(shift, 1) or indep - shift >= 3, (indep, shift)
    assert shift <= 3


# ======================================================================== RES-8: one split, one dip state
def test_all_runners_get_the_same_cutoff():
    """Same synthetic prices through backtest, features and forecast: one calendar (>= start_date) and one cutoff."""
    from dataclasses import replace as rep
    from test_backtest_run import META, synthetic
    from dipdash import backtest as bt
    from dipdash.backtest_run import freeze_spec
    prices, ix, uni, q, s = synthetic(n_stocks=3)
    cal = bt.shared_calendar(prices, s.backtest.start_date)
    assert cal and min(cal) >= pd.Timestamp(s.backtest.start_date)
    cut = bt.shared_cutoff(prices, s)
    assert cut == split_cutoff(cal, s.backtest.oos_fraction)
    all_dates = sorted({d for c in prices.values() for d in c.index})
    assert cut != split_cutoff(all_dates, s.backtest.oos_fraction), "start_date must matter (the old forecast ignored it)"
    assert freeze_spec(s, uni, META, cal)["split"]["cutoff"] == str(cut.date())                      # backtest
    assert bt.shared_cutoff(prices, rep(s, backtest=rep(s.backtest, oos_fraction=0.3))) > cut          # oos_fraction comes from settings
    for name in ("run_feature_experiment", "run_forecast_calibration"):                               # both scripts use the shared function
        mod = _load_script(name)
        assert mod.shared_cutoff is bt.shared_cutoff and mod.shared_calendar is bt.shared_calendar


def _load_script(name):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slow_slide(n=300, days=23, daily=-0.0075):
    """Flat, then a slow slide: about 13% below the 20-day high, no -4% day and no -7% five-day return."""
    c = np.concatenate([np.full(n, 100.0), 100.0 * (1 + daily) ** np.arange(1, days + 1)])
    return pd.Series(c, index=dates(len(c)))


def test_dip_state_includes_the_20d_rule():
    from dipdash.backtest import dip_state
    c = slow_slide()
    sig = signals(c, S)
    last = sig.iloc[-1]
    assert last["dd20"] <= -0.12 and last["dd20"] > -0.15, last["dd20"]
    assert last["r1"] > -S.dip.drop_1d and last["r5"] > -S.dip.drop_5d, "the slide must not trigger the 1d or 5d rule"
    assert bool(dip_state(c, S).iloc[-1]) is True
    old = (sig["r5"] <= -0.07) | (sig["r1"] <= -0.04)                          # the forecast runner's former hard-coded rule
    assert not old.iloc[-1]
    assert dip_state(c, S).equals(sig["dip"])
    assert not dip_state(c.iloc[:300], S).any()                                # flat: no flag


# ============================================================ RES-12a: null calibration (slow, opt in with DIP_SLOW=1)
def null_universe(seed, n_stocks=14, n=1100):
    """Null universe with a common factor and NO dip effect: r_i = beta_i * f + e_i, index = factor plus a little noise.
    Returns (prices, index_close, universe, quality, settings) ready for build_days. Synthetic only."""
    rng = np.random.default_rng(seed)
    idx = dates(n, "2026-10-29")
    f = rng.normal(0.0003, 0.010, n)
    prices, uni = {}, []
    for k in range(n_stocks):
        beta = rng.uniform(0.6, 1.4)
        r = beta * f + rng.normal(0.0, 0.012, n)
        prices[f"S{k}"] = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        uni.append(Stock(f"S{k}", f"S{k}", "US" if k % 2 == 0 else "Europe"))
    ix = {g: pd.Series(100 * np.exp(np.cumsum(f + rng.normal(0.0, 0.003, n))), index=idx) for g in (US, EU)}
    # placebo_draws as low as the path allows: only the ex_own interval is used here, and the placebos are computed but ignored
    s = replace(S, backtest=replace(S.backtest, start_date=str(idx[300].date()), horizons=(21,), bootstrap_draws=500, placebo_draws=20,
                                    seed=seed))
    return prices, ix, uni, {t: 70 if i % 2 else 40 for i, t in enumerate(prices)}, s


def null_replicate(seed):
    prices, ix, uni, q, s = null_universe(seed)
    days = build_days(prices, uni, ix, s, q)
    days = add_peer_returns(add_events(days, s), s.backtest.horizons)
    days, _ = add_periods(days, s)
    r = summarize(days, Cell("V1_price_only", 21, "All", "OOS"), s)
    return {"seed": seed, "n": r.get("n", 0), "months": r.get("n_months", 0), "est": r.get("ex_own", np.nan),
            "lo": r.get("ex_own_lo", np.nan), "hi": r.get("ex_own_hi", np.nan)}


@pytest.mark.skipif(os.environ.get("DIP_SLOW") != "1", reason="slow: set DIP_SLOW=1")
def test_primary_cell_false_positive_rate_near_nominal():
    """Under a null with a common factor, the 90% ex_own interval of the primary cell should exclude zero about 10% of the time.
    Band = 95% binomial band around 10% for the replicate count (200: 5.8-14.2%; 100: 4.1-15.9%)."""
    import time
    reps = int(os.environ.get("DIP_SLOW_REPS", "200"))
    band = {200: (0.058, 0.142), 100: (0.041, 0.159)}[reps]
    t0, rows = time.time(), []
    for seed in range(5000, 5000 + reps):
        rows.append(null_replicate(seed))
    df = pd.DataFrame(rows)
    ok = df.dropna(subset=["lo", "hi"])
    rate = float(((ok["lo"] > 0) | (ok["hi"] < 0)).mean())
    half = float(((ok["hi"] - ok["lo"]) / 2).mean())
    out = (f"RES12a replicates={reps} usable={len(ok)} rate={rate:.4f} band={band} runtime_s={time.time() - t0:.0f} "
           f"mean_events={ok['n'].mean():.1f} mean_months={ok['months'].mean():.1f} mean_width={2 * half:.5f} "
           f"mean_est={ok['est'].mean():.5f} sd_est={ok['est'].std():.5f} mean_half_width={half:.5f}")
    print(out)
    with open(os.environ.get("DIP_SLOW_OUT", os.devnull), "w") as fh:
        fh.write(out + "\n")
        df.to_csv(fh, index=False)
    assert len(ok) >= 0.95 * reps, out
    assert band[0] <= rate <= band[1], out
