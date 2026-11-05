"""RES-5 forward ledger: recording, idempotence, scoring and the honest summary. Synthetic data only; files under tmp_path."""
from dataclasses import replace
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from dipdash import ledger
from dipdash.config import load_settings
from dipdash.ledger import LEDGER_COLS, append_rows, ledger_rows, read_ledger, score, summarize_scores

NOW = datetime(2026, 11, 6, 0, 15, tzinfo=timezone.utc)


def row(t="AAA", asof="2026-11-05", dip=True, partial=False, q=80, setup="Quality dip", knife=False, region="US"):
    return {"t": t, "region": region, "asof": asof, "dip": dip, "partial": partial, "q": q, "setup": setup, "knife": knife}


def rows_df(*rows):
    return ledger_rows({"rows": list(rows)}, "sh", "uh", NOW)


def test_columns_are_fixed():
    assert LEDGER_COLS == ["asof", "ticker", "region", "flagged", "setup", "q", "knife", "settings_hash", "universe_hash", "recorded_at"]


def test_partial_rows_are_never_recorded():
    df = rows_df(row("AAA"), row("BBB", partial=True))
    assert list(df["ticker"]) == ["AAA"]


def test_unflagged_stocks_are_recorded_as_baseline():
    df = rows_df(row("AAA", dip=True), row("BBB", dip=False, setup="No dip", q=None))
    assert dict(zip(df["ticker"], df["flagged"])) == {"AAA": True, "BBB": False}


def test_a_later_complete_run_records_that_date(tmp_path):
    p = tmp_path / "ledger" / "flags.csv"
    assert append_rows(p, rows_df(row("AAA"), row("BBB", partial=True))) == 1
    assert append_rows(p, rows_df(row("AAA"), row("BBB"))) == 1          # BBB is now complete; AAA already there
    assert sorted(read_ledger(p)["ticker"]) == ["AAA", "BBB"]


def test_append_is_idempotent(tmp_path):
    p = tmp_path / "flags.csv"
    df = rows_df(row("AAA"), row("BBB", dip=False))
    assert append_rows(p, df) == 2
    before = p.read_bytes()
    assert append_rows(p, df) == 0
    assert p.read_bytes() == before


def test_first_complete_row_wins(tmp_path):
    p = tmp_path / "flags.csv"
    append_rows(p, rows_df(row("AAA", dip=True)))
    assert append_rows(p, rows_df(row("AAA", dip=False))) == 0
    assert bool(read_ledger(p)["flagged"].iloc[0]) is True


def test_append_never_rewrites_earlier_bytes(tmp_path):
    p = tmp_path / "flags.csv"
    append_rows(p, rows_df(row("AAA", asof="2026-11-04")))
    old = p.read_bytes()
    append_rows(p, rows_df(row("AAA", asof="2026-11-05")))
    new = p.read_bytes()
    assert new.startswith(old) and len(new) > len(old)
    assert new.count(b"asof") == 1                                       # header written once, when the file was new


def test_newlines_are_unix(tmp_path):
    p = tmp_path / "flags.csv"
    append_rows(p, rows_df(row("AAA"), row("BBB")))
    assert b"\r" not in p.read_bytes()


def test_unterminated_last_line_does_not_glue_rows(tmp_path):
    p = tmp_path / "flags.csv"
    append_rows(p, rows_df(row("AAA", asof="2026-11-04")))
    with p.open("ab") as fh:
        fh.write(b"2026-11-04,BBB,US,Tr")                                # a crash in the middle of a row
    append_rows(p, rows_df(row("BBB", asof="2026-11-04"), row("CCC", asof="2026-11-04")))
    assert "2026-11-04,BBB,US,Tr" in p.read_bytes().decode().split("\n")   # the broken piece stays on its own line
    assert sorted(read_ledger(p)["ticker"]) == ["AAA", "BBB", "CCC"]       # the complete BBB row was still recorded


def test_corrupt_file_raises_and_is_not_changed(tmp_path):
    p = tmp_path / "flags.csv"
    p.write_text("this,is,not,a,ledger\n1,2,3,4,5\n", encoding="utf-8")
    before = p.read_bytes()
    with pytest.raises(ValueError):
        append_rows(p, rows_df(row("AAA")))
    assert p.read_bytes() == before


def test_broken_row_in_the_middle_raises(tmp_path):
    p = tmp_path / "flags.csv"
    append_rows(p, rows_df(row("AAA")))
    with p.open("ab") as fh:
        fh.write(b"junk\n")
    before = p.read_bytes()
    with pytest.raises(ValueError):
        append_rows(p, rows_df(row("BBB")))
    assert p.read_bytes() == before


def _prices(closes, start="2026-11-02"):
    return pd.Series(closes, index=pd.bdate_range(start, periods=len(closes)))


def _scored_input(asof, flagged, ticker="AAA"):
    return pd.DataFrame({"asof": [asof], "ticker": [ticker], "flagged": [flagged]})


def test_score_known_answer():
    px = {"AAA": _prices([100, 100, 110, 121, 121])}        # Nov 2..6; signal on Nov 2
    out = score(_scored_input("2026-11-02", True), px, horizons=(1, 2))
    assert out["entry_date"].iloc[0] == "2026-11-03"        # first bar strictly after asof: close 100
    assert out["fwd_1"].iloc[0] == pytest.approx(0.10)      # 110/100 - 1
    assert out["fwd_2"].iloc[0] == pytest.approx(0.21)


def test_score_without_a_later_bar_is_empty():
    px = {"AAA": _prices([100, 100, 110, 121, 121])}
    out = score(_scored_input("2026-11-06", True), px, horizons=(1,))
    assert pd.isna(out["fwd_1"].iloc[0]) and not out["entry_date"].iloc[0]


def test_score_leaves_unmatured_rows_empty():
    px = {"AAA": _prices([100, 100, 110])}
    out = score(_scored_input("2026-11-02", True), px, horizons=(1, 5))
    assert out["fwd_1"].iloc[0] == pytest.approx(0.10)
    assert pd.isna(out["fwd_5"].iloc[0])


def test_score_keeps_stock_missing_from_prices():
    out = score(_scored_input("2026-11-02", True, ticker="GONE"), {"AAA": _prices([1, 2, 3])}, horizons=(1,))
    assert len(out) == 1 and pd.isna(out["fwd_1"].iloc[0])


def _scored_panel(n_dates=40, effect=0.02, seed=1):
    """One flagged and two unflagged stocks per date; flagged return = same-date level + effect (plus noise)."""
    rng = np.random.default_rng(seed)
    recs = []
    for d in pd.bdate_range("2026-01-05", periods=n_dates):
        base = rng.normal(0.0, 0.01)
        day = d.strftime("%Y-%m-%d")
        recs.append((day, "F0", True, base + effect + rng.normal(0, 0.005)))
        for k in range(2):
            recs.append((day, f"U{k}", False, base + rng.normal(0, 0.005)))
    return pd.DataFrame(recs, columns=["asof", "ticker", "flagged", "fwd_5"])


def test_summary_reports_n_costs_baseline_and_interval():
    s = load_settings()
    r = summarize_scores(_scored_panel(), s).iloc[0]
    assert r["horizon"] == 5 and r["n_flagged"] == 40 and r["n_baseline"] == 80
    assert r["n_months"] >= 2
    assert r["gross_diff"] == pytest.approx(0.02, abs=0.005)
    assert r["net_diff"] == pytest.approx(r["gross_diff"] - s.backtest.cost_roundtrip)
    assert r["net_lo"] < r["net_diff"] < r["net_hi"]
    assert r["note"] == ""


def test_summary_baseline_is_same_date_only():
    df = pd.DataFrame({"asof": ["2026-01-05"] * 2 + ["2026-02-02"] * 2 + ["2026-03-02"] * 2,
                       "ticker": ["F", "U"] * 3, "flagged": [True, False] * 3,
                       "fwd_5": [0.51, 0.50, -0.29, -0.30, 0.11, 0.10]})
    assert summarize_scores(df, load_settings()).iloc[0]["gross_diff"] == pytest.approx(0.01)


def test_summary_says_too_few_under_30():
    r = summarize_scores(_scored_panel(n_dates=29), load_settings()).iloc[0]
    assert "too few" in r["note"].lower()
    assert pd.isna(r["net_lo"]) and pd.isna(r["net_hi"]) and pd.isna(r["gross_lo"]) and pd.isna(r["gross_hi"])
    assert r["n_flagged"] == 29


def test_summary_horizon_with_no_matured_rows():
    df = _scored_panel(n_dates=5)
    df["fwd_21"] = np.nan
    out = summarize_scores(df, load_settings())
    r = out[out["horizon"] == 21].iloc[0]
    assert r["n_flagged"] == 0 and "too few" in r["note"].lower()


def test_settings_hash_follows_only_the_screen_sections():
    s = load_settings()
    h = ledger.settings_hash(s)
    assert len(h) == 16 and h == ledger.settings_hash(load_settings())
    assert ledger.settings_hash(replace(s, news=replace(s.news, fetch_if_5d_drop=0.5))) == h
    assert ledger.settings_hash(replace(s, dip=replace(s.dip, drop_1d=0.5))) != h


def test_universe_hash_is_file_sha256(tmp_path):
    p = tmp_path / "u.csv"
    p.write_bytes(b"ticker\nAAA\n")
    import hashlib
    assert ledger.file_hash(p) == hashlib.sha256(b"ticker\nAAA\n").hexdigest()
