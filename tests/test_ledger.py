"""RES-5 forward ledger: recording, idempotence, scoring and the honest summary. Synthetic data only; files under tmp_path."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dipdash import ledger
from dipdash.config import load_settings
from dipdash.ledger import LEDGER_COLS, append_rows, ledger_rows, prepare_rows, read_ledger, record_run, score, summarize_scores

NOW = datetime(2026, 11, 6, 0, 15, tzinfo=timezone.utc)


def row(t="AAA", asof="2026-11-05", dip=True, partial=False, q=80, setup="Quality dip", knife=False, region="US"):
    return {"t": t, "region": region, "asof": asof, "dip": dip, "partial": partial, "q": q, "setup": setup, "knife": knife}


def rows_df(*rows):
    return ledger_rows({"rows": list(rows)}, "sh", "uh", NOW)


def test_columns_are_fixed():
    assert LEDGER_COLS == ["asof", "ticker", "region", "flagged", "setup", "q", "knife", "settings_hash", "universe_hash",
                           "code_hash", "schema_version", "detail", "recorded_at"]


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


def _scored_panel(n_dates=300, effect=0.02, seed=1, setup="Quality dip"):
    """One flagged and two unflagged stocks per date (a new flagged stock each night, so the cooldown keeps all);
    flagged return = same-date level + effect plus noise. 300 weekdays is about 14 calendar months."""
    rng = np.random.default_rng(seed)
    recs = []
    for i, d in enumerate(pd.bdate_range("2026-01-05", periods=n_dates)):
        base = rng.normal(0.0, 0.01)
        day = d.strftime("%Y-%m-%d")
        recs.append((day, f"F{i}", True, setup, base + effect + rng.normal(0, 0.005)))
        for k in range(2):
            recs.append((day, f"U{k}", False, "No dip", base + rng.normal(0, 0.005)))
    return pd.DataFrame(recs, columns=["asof", "ticker", "flagged", "setup", "fwd_5"])


def _get(out, section="any dip", view="after cooldown", h=5):
    return out[(out["section"] == section) & (out["view"] == view) & (out["horizon"] == h)].iloc[0]


def test_summary_reports_n_costs_baseline_and_interval():
    s = load_settings()
    r = _get(summarize_scores(_scored_panel(), s))
    assert r["n_flagged"] == 300 and r["n_baseline"] == 600 and r["n_months"] >= 12
    assert r["gross_diff"] == pytest.approx(0.02, abs=0.005)
    assert r["net_diff"] == pytest.approx(r["gross_diff"] - s.backtest.cost_roundtrip)
    assert r["net_diff_2x"] == pytest.approx(r["gross_diff"] - 2 * s.backtest.cost_roundtrip)
    assert r["net_lo"] < r["net_diff"] < r["net_hi"] and r["note"] == ""
    assert r["p10_excess"] < r["med_excess"] < r["p90_excess"]


def test_summary_baseline_is_same_date_only():
    df = pd.DataFrame({"asof": ["2026-01-05"] * 2 + ["2026-02-02"] * 2 + ["2026-03-02"] * 2,
                       "ticker": ["F", "U"] * 3, "flagged": [True, False] * 3,
                       "fwd_5": [0.51, 0.50, -0.29, -0.30, 0.11, 0.10]})
    assert summarize_scores(df, load_settings()).iloc[0]["gross_diff"] == pytest.approx(0.01)


def test_summary_says_too_few_under_30_events():
    r = _get(summarize_scores(_scored_panel(n_dates=29), load_settings()))
    assert "too few" in r["note"].lower()
    assert pd.isna(r["net_lo"]) and pd.isna(r["net_hi"]) and pd.isna(r["gross_lo"]) and pd.isna(r["gross_hi"])
    assert r["n_flagged"] == 29 and not pd.isna(r["gross_diff"])


def test_summary_needs_twelve_months_even_with_many_events():
    r = _get(summarize_scores(_scored_panel(n_dates=180), load_settings()))        # about 8 months, 180 events
    assert r["n_flagged"] == 180 and r["n_months"] < 12 and "too few" in r["note"].lower() and pd.isna(r["net_lo"])


def test_summary_horizon_with_no_matured_rows():
    df = _scored_panel(n_dates=5)
    df["fwd_21"] = np.nan
    r = _get(summarize_scores(df, load_settings()), h=21)
    assert r["n_flagged"] == 0 and "too few" in r["note"].lower()


def test_cooldown_counts_trading_days_in_the_price_series_not_ledger_rows():
    s = load_settings()                                          # cooldown_days 21
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=60)]
    led = pd.concat([pd.DataFrame({"asof": dates, "ticker": "AAA", "flagged": True, "setup": "Quality dip"}),
                     pd.DataFrame({"asof": dates, "ticker": "BASE", "flagged": False, "setup": "No dip"})], ignore_index=True)
    px = {t: pd.Series(np.linspace(100, 160, 80), index=pd.bdate_range("2026-01-05", periods=80)) for t in ("AAA", "BASE")}
    out = summarize_scores(score(led, px, (5,)), s)
    assert _get(out)["n_flagged"] == 3 and _get(out, view="all nights")["n_flagged"] == 60     # bars 0, 21, 42
    gap = led[~((led["ticker"] == "AAA") & led["asof"].isin(dates[1:20]))]                            # ledger rows missing, bars still count
    assert _get(summarize_scores(score(gap, px, (5,)), s))["n_flagged"] == 3


def test_all_nights_interval_needs_the_cooldown_view_to_qualify():
    df = _scored_panel(n_dates=300)
    df["ticker"] = np.where(df["flagged"], "SAME", df["ticker"])  # one stock flagged every night: 15 events after cooldown
    out = summarize_scores(df, load_settings())
    c, a = _get(out), _get(out, view="all nights")
    assert c["n_flagged"] < 30 and pd.isna(c["net_lo"]) and a["n_flagged"] == 300 and pd.isna(a["net_lo"]) and a["note"]


def test_quality_dip_section_is_separate():
    df = _scored_panel()
    df.loc[df.index[df["flagged"]][:100], "setup"] = "Dip, low quality"
    out = summarize_scores(df, load_settings())
    assert _get(out, "any dip")["n_flagged"] == 300 and _get(out, "Quality dip only")["n_flagged"] == 200


def test_rule_versions_are_never_pooled():
    a, b = _scored_panel(), _scored_panel(seed=2, effect=-0.02)
    a["settings_hash"], b["settings_hash"] = "v1", "v2"
    out = summarize_scores(pd.concat([a, b], ignore_index=True), load_settings())
    assert set(out["settings_hash"]) == {"v1", "v2"}
    assert _get(out[out["settings_hash"] == "v1"])["gross_diff"] > 0.01
    assert _get(out[out["settings_hash"] == "v2"])["gross_diff"] < -0.01


def test_late_recorded_rows_are_excluded_and_counted():
    px = {"AAA": _prices([100, 100, 110, 121, 121, 121, 121, 121]), "BBB": _prices([100] * 8)}
    led = pd.DataFrame({"asof": ["2026-11-02", "2026-11-02"], "ticker": ["AAA", "BBB"], "flagged": [True, False],
                        "recorded_at": ["2026-11-05T22:00:00Z", "2026-11-02T22:00:00Z"]})
    sc = score(led, px, (1,))
    assert list(sc["late"]) == [True, False]                      # entry bar is Nov 3; AAA was recorded on Nov 5
    r = summarize_scores(sc, load_settings()).iloc[0]
    assert r["n_flagged"] == 0 and r["n_late"] == 1


def test_unscored_rows_old_enough_to_have_matured_are_counted():
    px = {"AAA": _prices([100, 100, 110, 121, 121, 121, 121]), "GONE": _prices([100, 100]), "BASE": _prices([100] * 7)}
    led = pd.DataFrame({"asof": ["2026-11-02"] * 3, "ticker": ["AAA", "GONE", "BASE"], "flagged": [True, True, False]})
    sc = score(led, px, (2,))
    assert sc.loc[sc.ticker == "GONE", "due_2"].iloc[0] and pd.isna(sc.loc[sc.ticker == "GONE", "fwd_2"].iloc[0])
    r = summarize_scores(sc, load_settings()).iloc[0]
    assert r["n_flagged"] == 1 and r["n_unscored"] == 1


def test_score_rejects_a_row_older_than_the_pull_and_a_late_entry():
    px = {"AAA": _prices([100, 100, 110, 121, 121])}
    old = score(_scored_input("2026-03-02", True), px, (1,))
    assert old["reason"].iloc[0] == "no_bar_at_asof" and pd.isna(old["fwd_1"].iloc[0]) and old["entry_date"].iloc[0] == ""
    halt = pd.Series([100, 100, 105, 106], index=pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-25", "2026-03-26"]))
    h = score(_scored_input("2026-03-03", True), {"AAA": halt}, (1,))
    assert h["reason"].iloc[0] == "entry_gap_over_7_days" and pd.isna(h["fwd_1"].iloc[0])


def test_settings_hash_follows_only_the_screen_sections():
    s = load_settings()
    h = ledger.settings_hash(s)
    assert len(h) == 16 and h == ledger.settings_hash(load_settings())
    assert ledger.settings_hash(replace(s, news=replace(s.news, fetch_if_5d_drop=0.5))) == h
    assert ledger.settings_hash(replace(s, dip=replace(s.dip, drop_1d=0.5))) != h


def test_universe_hash_is_file_sha256_with_line_endings_normalised(tmp_path):
    p, q = tmp_path / "u.csv", tmp_path / "v.csv"
    p.write_bytes(b"ticker\nAAA\n")
    q.write_bytes(b"ticker\r\nAAA\r\n")
    import hashlib
    assert ledger.file_hash(p) == hashlib.sha256(b"ticker\nAAA\n").hexdigest() == ledger.file_hash(q)


def test_detail_holds_the_unrecoverable_signal_data():
    r = row("AAA") | {"price": 12.3, "r1": -0.05, "r5": -0.08, "dd20": -0.13, "vs200": -0.1, "dd52": -0.2, "why": ["1d drop"],
                      "q_status": "ok", "q_scored": 6, "q_applicable": 6, "q_passed": 5, "q_must_failed": [], "q_must_missing": [],
                      "earn": {"next": "2026-12-01"}, "name": "not stored"}
    df, _ = prepare_rows({"rows": [r]}, "sh", "uh", NOW, code="cc", price_source={"AAA": "primary"})
    d = json.loads(df["detail"].iloc[0])
    assert d["price"] == 12.3 and d["why"] == ["1d drop"] and d["price_source"] == "primary" and d["earn"] == {"next": "2026-12-01"}
    assert "name" not in d and df["code_hash"].iloc[0] == "cc" and df["schema_version"].iloc[0] == "1"


def test_older_header_is_read_by_name_and_unknown_header_is_refused(tmp_path):
    p = tmp_path / "flags.csv"
    p.write_text("asof,ticker,region,flagged,setup,q,knife,settings_hash,universe_hash,recorded_at\n"
                 "2026-11-04,AAA,US,True,Quality dip,80,False,s,u,2026-11-05T00:00:00Z\n", encoding="utf-8", newline="")
    assert append_rows(p, rows_df(row("BBB", asof="2026-11-04"))) == 1
    got = read_ledger(p)
    assert sorted(got["ticker"]) == ["AAA", "BBB"] and got["detail"].iloc[0] == ""
    assert len(p.read_text(encoding="utf-8").splitlines()[2].split(",")) == 10          # the row follows the file's own header
    bad = tmp_path / "bad.csv"
    bad.write_text("asof,ticker,mystery,recorded_at\n", encoding="utf-8")
    with pytest.raises(ValueError):
        append_rows(bad, rows_df(row("AAA")))


def test_bom_in_header_is_read_and_appending_continues(tmp_path):
    p = tmp_path / "flags.csv"
    append_rows(p, rows_df(row("AAA", asof="2026-11-04")))
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    before = p.read_bytes()
    assert append_rows(p, rows_df(row("BBB", asof="2026-11-04"))) == 1
    assert p.read_bytes().startswith(before) and sorted(read_ledger(p)["ticker"]) == ["AAA", "BBB"]


def test_read_ledger_dedupes_first_wins(tmp_path):
    p = tmp_path / "flags.csv"
    append_rows(p, rows_df(row("AAA", dip=True)))
    with p.open("ab") as fh:                                      # a duplicate written by some other tool
        fh.write(p.read_bytes().splitlines()[1].replace(b"True", b"False", 1) + b"\n")
    got = read_ledger(p)
    assert len(got) == 1 and bool(got["flagged"].iloc[0]) is True


def test_run_too_soon_after_the_close_is_not_recorded():
    cet = timezone(timedelta(hours=1))
    r = row("SEB.ST", asof="2026-11-05", region="Europe")
    started = datetime(2026, 11, 5, 17, 25, tzinfo=cet)         # price taken at 17:25 CET; validation finishes at 17:46
    df, skipped = prepare_rows({"rows": [r]}, "s", "u", datetime(2026, 11, 5, 17, 46, tzinfo=cet), run_started=started)
    assert df.empty and skipped == {"SEB.ST": "too_soon"}
    later, _ = prepare_rows({"rows": [r]}, "s", "u", NOW, run_started=datetime(2026, 11, 5, 19, 31, tzinfo=cet))
    assert list(later["ticker"]) == ["SEB.ST"]


def test_record_run_keeps_versions_runs_log_and_backup(tmp_path):
    uni, st = tmp_path / "universe.csv", tmp_path / "settings.toml"
    uni.write_bytes(b"ticker,name,region\r\nAAA,A,US\r\n")
    st.write_text("[dip]\n", encoding="utf-8")
    led = tmp_path / "ledger" / "flags.csv"
    payload = {"rows": [row("AAA"), row("BBB", partial=True)], "data_quality": [{"t": "CCC", "reason": "stale", "detail": "x"}]}
    kw = dict(settings_path=st, run_started=datetime(2026, 11, 6, 0, 15, tzinfo=timezone.utc), now=NOW, universe_size=3)
    assert record_run(payload, load_settings(), uni, led, **kw) == 1
    vdir = led.parent / "versions"
    assert (vdir / f"{ledger.settings_hash(load_settings())}.toml").read_text() == "[dip]\n"
    uh = ledger.file_hash(uni)
    assert (vdir / f"{uh}.csv").exists() and not led.with_name("flags.backup.csv").exists()
    uni.write_bytes(b"changed")
    kept = (vdir / f"{uh}.csv").read_bytes()
    record_run(payload, load_settings(), uni, led, **kw)
    assert (vdir / f"{uh}.csv").read_bytes() == kept and led.with_name("flags.backup.csv").exists()
    runs = pd.read_csv(led.parent / "runs.csv", dtype=str)
    assert len(runs) == 2 and runs["rows_written"].tolist() == ["1", "0"] and runs["partial_count"].iloc[0] == "1"
    assert json.loads(runs["skipped"].iloc[0]) == {"BBB": "partial", "CCC": "stale"} and runs["universe_size"].iloc[0] == "3"


def test_corrupt_ledger_does_not_replace_the_backup(tmp_path):
    uni = tmp_path / "universe.csv"
    uni.write_text("ticker\nAAA\n", encoding="utf-8")
    led = tmp_path / "flags.csv"
    record_run({"rows": [row("AAA")]}, load_settings(), uni, led, now=NOW)
    record_run({"rows": [row("AAA", asof="2026-11-04")]}, load_settings(), uni, led, now=NOW)
    good = led.with_name("flags.backup.csv").read_bytes()
    led.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(ValueError):
        record_run({"rows": [row("ZZZ")]}, load_settings(), uni, led, now=NOW)
    assert led.with_name("flags.backup.csv").read_bytes() == good


def test_pick_raw_skips_a_mid_session_pull():
    files = [Path("2026-11-05.csv.gz"), Path("2026-11-06.csv.gz"), Path("2026-11-06_143000.csv.gz")]
    pick, warn = ledger.pick_raw(files)
    assert pick.name == "2026-11-06.csv.gz" and "mid-session" in warn
    assert ledger.pick_raw(files[:2]) == (files[1], "")


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("score_ledger", Path(__file__).resolve().parents[1] / "scripts" / "score_ledger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_score_script_text_has_no_banned_phrase_and_states_the_limits():
    mod = _load_script()
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_wording", Path(mod.__file__).with_name("check_wording.py"))
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)
    assert cw.scan_text(Path(mod.__file__).read_text(encoding="utf-8")) == []
    text = "\n".join(mod.explain(0.001, 0.9, 21)) + mod.CAVEAT
    for needle in ("round trip", "Gross", "Net", "Survivorship bias", "unscored", "85 to 91%"):
        assert needle in text


def test_score_script_runs_on_a_synthetic_ledger(tmp_path, capsys):
    from dipdash.cache import save_raw_prices
    mod = _load_script()
    idx = pd.bdate_range("2026-01-05", periods=80)
    px = {t: (pd.Series(np.linspace(100, 120, 80), index=idx), None) for t in ("AAA", "BBB")}
    raw = save_raw_prices(px, "yfinance", tmp_path / "raw")
    dates = [d.strftime("%Y-%m-%d") for d in idx[:10]]
    for d in dates:
        append_rows(tmp_path / "flags.csv", rows_df(row("AAA", asof=d), row("BBB", asof=d, dip=False, setup="No dip")))
    assert mod.main(["--ledger", str(tmp_path / "flags.csv"), "--raw", str(raw), "--out", str(tmp_path / "o.csv")]) == 0
    out = capsys.readouterr().out
    assert "needs years of nights before the result can mean much" in out and "not advice" in out and "too few for an interval" in out
    assert (tmp_path / "o.csv").exists()
    assert mod.main(["--ledger", str(tmp_path / "none.csv"), "--raw", str(raw)]) == 1


@pytest.mark.parametrize("asof,season", [("2026-01-15", "winter"), ("2026-07-15", "summer")])
def test_nightly_run_records_us_and_european_rows_in_both_seasons(asof, season):
    from zoneinfo import ZoneInfo
    hel = ZoneInfo("Europe/Helsinki")
    nxt = (pd.Timestamp(asof) + pd.Timedelta(days=1)).date()
    start = datetime(nxt.year, nxt.month, nxt.day, 0, 15, tzinfo=hel)          # the scheduled time
    payload = {"rows": [row("AAA", asof=asof), row("SEB.ST", asof=asof, region="Europe")]}
    for when in (start, start + timedelta(minutes=20)):                         # the run and its retry
        df, skipped = prepare_rows(payload, "s", "u", when, run_started=when)
        assert sorted(df["ticker"]) == ["AAA", "SEB.ST"] and skipped == {}, season


def test_forty_five_minutes_after_the_us_close_is_not_recorded():
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    started = datetime(2026, 7, 15, 16, 45, tzinfo=ny)
    df, skipped = prepare_rows({"rows": [row("AAA", asof="2026-07-15")]}, "s", "u", started, run_started=started)
    assert df.empty and skipped == {"AAA": "too_soon"}
    ok = datetime(2026, 7, 15, 17, 0, tzinfo=ny)                                # exactly 60 minutes passes
    assert len(prepare_rows({"rows": [row("AAA", asof="2026-07-15")]}, "s", "u", ok, run_started=ok)[0]) == 1


def test_missing_columns_names_what_an_older_header_lacks(tmp_path):
    p = tmp_path / "flags.csv"
    assert ledger.missing_columns(p) == []
    p.write_text("asof,ticker,region,flagged,setup,q,knife,settings_hash,universe_hash,recorded_at\n", encoding="utf-8")
    assert ledger.missing_columns(p) == ["code_hash", "schema_version", "detail"]
    p.write_text(",".join(LEDGER_COLS) + "\n", encoding="utf-8")
    assert ledger.missing_columns(p) == []


def test_runs_log_failure_is_its_own_error_and_rows_stay_written(tmp_path):
    uni = tmp_path / "universe.csv"
    uni.write_text("ticker\nAAA\n", encoding="utf-8")
    led = tmp_path / "ledger" / "flags.csv"
    (tmp_path / "ledger").mkdir()
    (tmp_path / "ledger" / "runs.csv").mkdir()                                  # cannot be opened as a file
    with pytest.raises(ledger.RunsLogError):
        record_run({"rows": [row("AAA")]}, load_settings(), uni, led, now=NOW)
    assert list(read_ledger(led)["ticker"]) == ["AAA"]
