"""Market-model residual move: known-answer tests on synthetic data (no network)."""
import numpy as np
import pandas as pd
import pytest

from dipdash.data import fetch_indices
from dipdash.residual import residual_move
from synth import dates

N = 400


def _index(n=N, seed=1, end=None):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0003, 0.01, n)
    r[-5:] = 0.0
    idx = dates(n) if end is None else dates(n, end)
    return pd.Series(100 * np.cumprod(1 + r), index=idx)


def _stock_from(index, beta=1.5, noise=0.002, seed=2):
    """close built from index daily returns: r_s = beta*r_i + noise."""
    rng = np.random.default_rng(seed)
    ri = index.pct_change().fillna(0).to_numpy()
    rs = beta * ri + rng.normal(0, noise, len(ri))
    return pd.Series(100 * np.cumprod(1 + rs), index=index.index)


def _set_last_returns(index, stock, ri_last, rs_last):
    """Overwrite the final 1-day returns of both series (leaves earlier bars alone)."""
    i, s = index.copy(), stock.copy()
    i.iloc[-1] = i.iloc[-2] * (1 + ri_last)
    s.iloc[-1] = s.iloc[-2] * (1 + rs_last)
    return i, s


def test_beta_recovered():
    ix = _index()
    out = residual_move(_stock_from(ix, 1.5), ix)
    assert out["reason"] is None
    assert out["beta"] == pytest.approx(1.5, abs=0.05)


def test_systematic_drop_has_near_zero_residual():
    ix = _index()
    ix2, st2 = _set_last_returns(ix, _stock_from(ix, 1.5, noise=0.0005), -0.04, -0.06)
    out = residual_move(st2, ix2)
    assert out["res1"] == pytest.approx(0.0, abs=0.004)
    assert abs(out["res5z"]) < 1.0


def test_idiosyncratic_drop_is_the_residual():
    ix = _index()
    ix2, st2 = _set_last_returns(ix, _stock_from(ix, 1.5, noise=0.0005), 0.0, -0.08)
    out = residual_move(st2, ix2)
    assert out["res1"] == pytest.approx(-0.08, abs=0.004)
    assert out["res5"] == pytest.approx(-0.08, abs=0.006)
    assert out["res5z"] < -5            # tiny noise, huge move


def test_drop_in_last_5_bars_does_not_change_beta():
    ix = _index()
    base = _stock_from(ix, 1.5)
    crashed = base.copy()
    crashed.iloc[-3:] = crashed.iloc[-4] * np.array([0.8, 0.7, 0.6])    # -40% inside the measured window
    worse = base.copy()
    worse.iloc[-3:] = worse.iloc[-4] * np.array([0.6, 0.5, 0.4])
    a, b, c = residual_move(base, ix), residual_move(crashed, ix), residual_move(worse, ix)
    assert b["beta"] == a["beta"] == c["beta"]
    assert b["res5"] < -0.3
    # residual vol (the z denominator) is untouched by the crash: z / res5 is identical for two different crashes
    assert b["res5z"] / b["res5"] == pytest.approx(c["res5z"] / c["res5"], rel=2e-3)


def test_too_short_history_returns_none_with_reason():
    ix = _index(100)
    out = residual_move(_stock_from(ix), ix)
    assert out["beta"] is None and out["res5"] is None and out["res1"] is None and out["res5z"] is None
    assert "history" in out["reason"]


def test_misaligned_dates_use_common_dates_only():
    ix = _index()
    st = _stock_from(ix, 1.5)
    st_gappy = st.drop(st.index[100:140:3])       # the stock lacks some days the index has
    out = residual_move(st_gappy, ix)
    assert out["reason"] is None
    assert out["beta"] == pytest.approx(1.5, abs=0.15)      # multi-day returns on gaps, still near the truth


def test_constant_index_returns_none():
    ix = pd.Series(100.0, index=dates(N))
    out = residual_move(_stock_from(_index(), 1.0), ix)
    assert out["beta"] is None and out["res5"] is None
    assert "variance" in out["reason"]


def test_lagged_stock_bar_uses_index_move_ending_on_stocks_last_date():
    ix = _index()
    st = _stock_from(ix, 1.0, noise=0.0005)
    ix2, st2 = _set_last_returns(ix, st, -0.10, -0.10)     # index crashes on the LAST day
    lagged = st2.iloc[:-1]                                  # stock bar for that last day has not arrived
    out = residual_move(lagged, ix2)
    # the index's final -10% is in the future relative to the stock's last bar and must not be used
    assert out["asof"] == str(lagged.index[-1])[:10]
    exp5 = lagged.iloc[-1] / lagged.iloc[-6] - 1 - out["beta"] * (ix2.loc[lagged.index[-1]] / ix2.loc[lagged.index[-6]] - 1)
    assert out["res5"] == pytest.approx(exp5, abs=1e-4)
    assert abs(out["res5"]) < 0.01


def test_index_missing_the_stocks_last_day_returns_none():
    ix = _index()
    out = residual_move(_stock_from(ix), ix.iloc[:-1])
    assert out["res5"] is None and "last bar" in out["reason"]


def test_beta_is_clipped_and_flagged():
    ix = _index()
    out = residual_move(_stock_from(ix, 5.0, noise=0.001), ix)
    assert out["beta"] == 3.0 and out["beta_raw"] == pytest.approx(5.0, abs=0.2)


def test_fetch_indices_can_hand_back_long_history_without_changing_rows():
    from dipdash.config import IndexSpec
    spec = IndexSpec("^GSPC", "S&P 500", "US")
    close = _index(300)
    hist: dict = {}
    got = fetch_indices([spec], lambda s: close, history=hist)
    assert len(got[0]["closes"]) == 12                     # payload shape unchanged
    assert list(hist) == ["^GSPC"] and len(hist["^GSPC"]) == 300


def test_timezone_aware_index_dates_still_align():
    ix = _index()
    ix_tz = ix.copy()
    ix_tz.index = ix.index.tz_localize("Europe/Helsinki")        # Yahoo index history comes back exchange-local
    out = residual_move(_stock_from(ix, 1.5), ix_tz)
    assert out["reason"] is None and out["beta"] == pytest.approx(1.5, abs=0.05)


# ---- regressions from the independent review (2026-11-04) -----------------------------------------------------
def test_a_duplicated_date_in_the_stock_series_does_not_abort():
    ix = _index()
    st = _stock_from(ix)
    dup = pd.concat([st, st.iloc[[-3]]]).sort_index(kind="stable")      # one date appears twice
    out = residual_move(dup, ix)
    assert out["reason"] is None and out["beta"] == pytest.approx(1.5, abs=0.1)


def test_unsorted_input_gives_the_same_answer():
    ix = _index()
    st = _stock_from(ix)
    a = residual_move(st, ix)
    b = residual_move(st.iloc[::-1], ix.iloc[::-1])
    assert a["res5"] == b["res5"] and a["beta"] == b["beta"]


def test_negative_estimated_beta_is_floored_and_says_which_side():
    ix = _index()
    st = _stock_from(ix, beta=-0.8)
    out = residual_move(st, ix)
    assert out["beta"] == 0.0 and out["beta_raw"] < 0 and out["beta_clipped"] and out["beta_side"] == "floor"


def test_high_beta_is_capped_and_says_which_side():
    ix = _index()
    out = residual_move(_stock_from(ix, beta=3.6), ix)
    assert out["beta"] == 3.0 and out["beta_side"] == "cap"
    assert residual_move(_stock_from(ix, beta=1.2), ix)["beta_side"] is None


# ---- RES-9: standard error of beta -------------------------------------------------------------------------------
def test_beta_se_matches_statsmodels():
    sm = pytest.importorskip("statsmodels.api")
    from dipdash.residual import slope_se
    rng = np.random.default_rng(7)
    x = rng.normal(0, 0.01, 252)
    y = 1.1 * x + rng.normal(0, 0.012, 252)
    res = sm.OLS(y, sm.add_constant(x)).fit()
    beta = float(res.params[1])
    assert abs(slope_se(x, y, beta) - float(res.bse[1])) < 1e-9


def test_beta_se_covers_true_beta_about_95_percent():
    rng = np.random.default_rng(20261106)
    n = 258                                   # 257 returns, minus the 5 excluded -> 252 estimation returns
    idx = dates(n)
    hits = 0
    for _ in range(1000):
        ri = rng.normal(0, 0.01, n - 1)
        rs = 1.2 * ri + rng.normal(0, 0.01, n - 1)
        ix = pd.Series(100 * np.cumprod(np.r_[1.0, 1 + ri]), index=idx)
        st = pd.Series(100 * np.cumprod(np.r_[1.0, 1 + rs]), index=idx)
        out = residual_move(st, ix)
        assert out["reason"] is None and out["n_obs"] == 252
        hits += abs(out["beta_raw"] - 1.2) <= 1.96 * out["beta_se"]
    assert 0.93 <= hits / 1000 <= 0.97


def test_clipped_beta_is_not_market_adjusted():
    ix = _index()
    out = residual_move(_stock_from(ix, 5.0, noise=0.001), ix)
    assert out["beta"] == 3.0 and out["beta_clipped"] is True
    assert out["market_adjusted"] is False


def test_noisy_beta_is_not_market_adjusted():
    from dipdash.residual import BETA_SE_UNCERTAIN
    ix = _index()
    out = residual_move(_stock_from(ix, 1.2, noise=0.06), ix)     # residual sd ~6x the index sd
    assert out["reason"] is None
    assert out["beta_se"] > BETA_SE_UNCERTAIN == 0.25
    assert out["beta_clipped"] is False and out["beta"] == out["beta_raw"]    # raw beta is unclipped
    assert out["market_adjusted"] is False


def test_clean_beta_is_market_adjusted():
    ix = _index()
    out = residual_move(_stock_from(ix, 1.5, noise=0.002), ix)
    assert out["reason"] is None and out["beta_se"] is not None and out["beta_se"] < 0.25
    assert out["market_adjusted"] is True


def test_failure_returns_none_and_false():
    ix = _index(100)
    out = residual_move(_stock_from(ix), ix)
    assert out["beta_se"] is None and out["market_adjusted"] is False
    assert out["reason"] is not None
