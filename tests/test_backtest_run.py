import json
import re
from dataclasses import replace

import pandas as pd
import pytest

import dipdash.backtest_run as br
from dipdash.backtest import EU, US
from dipdash.backtest_report import md_table, pct, render_report, write_report
from dipdash.backtest_run import append_trials, freeze_spec, run_backtest
from test_backtest import S, universe  # synthetic random-walk universe with an optional planted effect

from dipdash.backtest import add_events, add_periods, add_peer_returns, build_days
from dipdash.config import Stock


def synthetic(seed=21, effect=0.0, n_stocks=14, n=1100):
    """The same generator as test_backtest, but returning the raw inputs run_backtest takes."""
    import numpy as np
    from synth import dates
    from dipdash.backtest import apply_cooldown, signals
    rng = np.random.default_rng(seed)
    idx = dates(n)
    base = replace(S, backtest=replace(S.backtest, start_date="2000-01-01"))
    prices, uni = {}, []
    for k in range(n_stocks):
        r = rng.normal(0.0003, 0.016, n)
        c = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        if effect:
            for i in np.flatnonzero(apply_cooldown(signals(c, base)["dip"].to_numpy(), 21)):
                if i + 7 < n:
                    r[i + 2:i + 7] += effect
            c = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        prices[f"S{k}"] = c
        uni.append(Stock(f"S{k}", f"S{k}", "US" if k % 2 == 0 else "Europe"))
    ix = {US: pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), index=idx),
          EU: pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))), index=idx)}
    s = replace(S, backtest=replace(S.backtest, start_date=str(idx[300].date()), horizons=(5, 21, 63), bootstrap_draws=300, placebo_draws=200))
    return prices, ix, uni, {t: 70 if i % 2 else 40 for i, t in enumerate(prices)}, s


META = {"source": "synthetic", "raw_file": "x", "raw_sha256": "0" * 8}


def test_spec_is_written_before_any_result_is_computed(tmp_path, monkeypatch):
    prices, ix, uni, q, s = synthetic()

    def boom(*a, **k):
        raise RuntimeError("stop before computing anything")

    monkeypatch.setattr(br, "build_days", boom)
    with pytest.raises(RuntimeError):
        run_backtest(prices, ix, uni, q, s, tmp_path / "run", META)
    spec = json.loads((tmp_path / "run" / "spec.json").read_text())
    assert spec["primary_cell"]["period"] == "OOS" and spec["spec_hash"]
    assert not (tmp_path / "run" / "results.csv").exists()


def test_spec_hash_is_stable_and_changes_with_any_frozen_choice():
    prices, ix, uni, q, s = synthetic()
    cal = sorted({d for c in prices.values() for d in c.index})
    h = freeze_spec(s, uni, META, cal)["spec_hash"]
    assert freeze_spec(s, uni, META, cal)["spec_hash"] == h
    assert freeze_spec(replace(s, dip=replace(s.dip, drop_5d=0.06)), uni, META, cal)["spec_hash"] != h
    assert freeze_spec(replace(s, backtest=replace(s.backtest, cooldown_days=10)), uni, META, cal)["spec_hash"] != h
    assert freeze_spec(s, uni, {**META, "raw_sha256": "1" * 8}, cal)["spec_hash"] != h


def test_full_run_writes_every_artifact_and_a_report_without_banned_wording(tmp_path):
    prices, ix, uni, q, s = synthetic(effect=0.006)
    out = tmp_path / "2026-11-02"
    run = run_backtest(prices, ix, uni, q, s, out, META, today=pd.Timestamp("2026-10-30").date())
    report = write_report(run, s, out)
    for f in ("spec.json", "results.csv", "events.csv", "data_validation.csv", "report.md", "distribution.png", "forest.png"):
        assert (out / f).exists() and (out / f).stat().st_size > 0, f
    assert (tmp_path / "trials.csv").exists()
    text = report.read_text(encoding="utf-8")
    for h in ("Pre-registered question", "How much to trust this", "Survivorship bias", "After costs", "Market-wide selloffs", "How many things were tried"):
        assert h in text
    assert not re.search(r"\bworks?\b|will (profit|pay|outperform|beat|earn)|buy now|\bsell\b|guarantee", text, re.I)
    assert "historically, in this sample" in text


def test_planted_effect_shows_up_in_the_report_and_a_null_run_is_labelled_not_met(tmp_path):
    prices, ix, uni, q, s = synthetic(effect=0.006)
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "a", META)
    assert "pre-registered condition is met" in render_report(run, s, {"distribution": "d.png", "forest": "f.png"})
    prices, ix, uni, q, s = synthetic(seed=22)
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "b", META)
    assert "not met" in render_report(run, s, {"distribution": "d.png", "forest": "f.png"})


def test_trial_log_appends_and_marks_the_primary_cell(tmp_path):
    prices, ix, uni, q, s = synthetic()
    run_backtest(prices, ix, uni, q, s, tmp_path / "r1", META)
    run_backtest(prices, ix, uni, q, s, tmp_path / "r2", META)
    log = pd.read_csv(tmp_path / "trials.csv")
    assert log["spec_hash"].nunique() == 1 and len(log) % 2 == 0           # the same spec twice: every cell logged twice
    assert log["primary"].sum() == 2 and log[log["primary"]]["period"].eq("OOS").all()
    assert set(log["variant"]) == set(br.VARIANTS)


def test_events_file_holds_only_event_days_with_their_forward_returns(tmp_path):
    prices, ix, uni, q, s = synthetic()
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "r", META)
    ev = pd.read_csv(tmp_path / "r" / "events.csv", parse_dates=["date", "entry_date"])
    assert len(ev) > 100 and (ev["entry_date"] > ev["date"]).all()                # entry is always after the signal date
    assert ev[[c for c in ev.columns if c.startswith("ev_")]].any(axis=1).all()


def test_formatting_helpers():
    assert pct(0.0123) == "+1.2%" and pct(-0.0123) == "−1.2%" and pct(0.0123, sign=False) == "1.2%" and pct(float("nan")) == "n/a" and pct(None) == "n/a"
    assert md_table(["a", "b"], [[1, 2]]).splitlines() == ["| a | b |", "|---|---|", "| 1 | 2 |"]


def test_clean_bars_removes_only_bars_that_did_not_trade():
    from dipdash.backtest_run import clean_bars
    from synth import dates
    c = pd.Series([10.0, 10.0, 99.0, 10.2, 10.3], index=dates(5))
    v = pd.Series([5.0, 0.0, 0.0, float("nan"), 7.0], index=dates(5))
    out, n = clean_bars(c, v)
    assert n == 2 and list(out) == [10.0, 10.2, 10.3]                       # zero volume dropped (placeholder and corrupt bar); missing volume kept
    same, none_removed = clean_bars(c, None)
    assert none_removed == 0 and list(same) == list(c)
    assert clean_bars(c.iloc[:0], v.iloc[:0])[1] == 0


def test_the_frozen_spec_records_the_revisions_and_both_placebos():
    prices, ix, uni, q, s = synthetic()
    cal = sorted({d for c in prices.values() for d in c.index})
    spec = freeze_spec(s, uni, META, cal)
    assert spec["revisions_after_first_look"] == []                         # a new spec never inherits another spec's history
    assert any("date-shift" in b for b in spec["baselines"]) and any("independent" in b for b in spec["baselines"])
    assert spec["spec_hash"] != "90205cfc6da3a007"


def test_specs_are_archived_by_hash_and_an_archived_spec_is_never_overwritten(tmp_path):
    prices, ix, uni, q, s = synthetic()
    out = tmp_path / "r"
    run = run_backtest(prices, ix, uni, q, s, out, META)
    h = run["spec"]["spec_hash"]
    archived = out / f"spec_{h}.json"
    assert archived.exists() and json.loads(archived.read_text())["spec_hash"] == h
    archived.write_text("sentinel")
    run_backtest(prices, ix, uni, q, s, out, META)                          # same analysis again
    assert archived.read_text() == "sentinel"                               # kept as it was
    s2 = replace(s, dip=replace(s.dip, drop_5d=0.06))
    run2 = run_backtest(prices, ix, uni, q, s2, out, META)
    assert (out / f"spec_{run2['spec']['spec_hash']}.json").exists() and run2["spec"]["spec_hash"] != h
    assert json.loads((out / "spec.json").read_text())["spec_hash"] == run2["spec"]["spec_hash"]       # spec.json is the latest


def test_descriptive_notes_do_not_change_the_spec_hash_but_every_frozen_choice_does(tmp_path):
    prices, ix, uni, q, s = synthetic()
    cal = sorted({d for c in prices.values() for d in c.index})
    base = freeze_spec(s, uni, META, cal)
    import hashlib
    notes = {"revisions_after_first_look", "sample_notes"}
    again = hashlib.sha256(json.dumps({k: v for k, v in base.items() if k not in notes | {"spec_hash"}}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    assert again == base["spec_hash"]


def test_the_trial_log_records_every_computed_cell_each_run(tmp_path):
    prices, ix, uni, q, s = synthetic(effect=0.006)
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "r", META)
    log = pd.read_csv(tmp_path / "trials.csv")
    assert len(log) == int((run["results"]["n"] > 0).sum()) and len(log) > 60
    assert set(log["group"]) == {"All", US, EU} and set(log["period"]) == {"ALL", "IS", "OOS", "OOS_exstress"}
    assert run["spec"]["cells_computed"] == 108


def test_report_has_the_tally_the_review_section_and_visible_signs_near_zero(tmp_path):
    from dipdash.backtest_report import bound
    assert bound(-0.0003) == "−0.03%" and bound(0.0004) == "+0.04%" and bound(0.0123) == "+1.2%" and bound(-0.0123) == "−1.2%"
    prices, ix, uni, q, s = synthetic(seed=23)
    out = tmp_path / "r"
    run = run_backtest(prices, ix, uni, q, s, out, META)
    text = write_report(run, s, out).read_text(encoding="utf-8")
    for h in ("In sample versus out of sample", "tally, not", "Independent review", "Reading the index column", "dividend-adjusted and the indices are price-only",
              "Low power", "Changes after the first look", "the least distorted comparison"):
        assert h in text, h
    assert not re.search(r"\bworks?\b|will (profit|pay|outperform|beat|earn)|buy now|\bsell\b|guarantee", text, re.I)


def test_a_trial_log_with_an_older_column_layout_is_set_aside_not_mixed(tmp_path):
    old = tmp_path / "trials.csv"
    old.write_text("run_at,spec_hash,variant,horizon,period,n,ex_own,ex_own_lo,ex_own_hi,primary\n2026-01-01 00:00,abc,V1_price_only,21,OOS,5,0.1,0.0,0.2,True\n", encoding="utf-8")
    prices, ix, uni, q, s = synthetic()
    run_backtest(prices, ix, uni, q, s, tmp_path / "r", META, trials_path=old)
    fresh = pd.read_csv(old)                                                    # parses: one consistent layout
    assert "group" in fresh.columns and "abc" not in set(fresh["spec_hash"])
    older = list(tmp_path.glob("trials_older_layout_*.csv"))
    assert len(older) == 1 and "abc" in older[0].read_text()                    # the earlier history is kept


# ---------------------------------------------------------------- RES-7: no hand-typed numbers in the report
OLD_LITERALS = ("0.2660", "1,504", "660 distinct", "ROG.SW", "KNEBV", "NOVO-B", "59 of 60", "Roche", "back to 2010")
CH = {"distribution": "d.png", "forest": "f.png"}


def test_report_has_no_literals_from_the_published_run_and_shows_this_runs_numbers(tmp_path):
    prices, ix, uni, q, s = synthetic(effect=0.006)
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "r", META)
    text = render_report(run, s, CH)
    for lit in OLD_LITERALS:
        assert lit not in text, lit
    prim = run["results"].query("variant == 'V1_price_only' and horizon == 21 and group == 'All' and period == 'OOS'").iloc[0]
    assert f"{int(prim['n']):,} events" in text
    assert f"{len(prices)} of {len(uni)}" not in text and f"All {len(uni)} stocks have price data" in text    # synthetic: nothing missing
    assert f"At most {int(prim['shift_lags']):,} distinct shifts were drawn" in text
    assert "Share of date-shifted comparisons that did as well as the real events" in text and "effective number of independent shifts is much smaller" in text
    assert "non-empty cells" in text
    assert "stats-reviewer" not in text and "These numbers have not been checked by a second person or tool; treat them as unreviewed." in text
    assert f"{s.backtest.cooldown_days}-bar cooldown" in text and f"{s.backtest.ci_level:.0%} bootstrap intervals" in text
    assert "No review is recorded for spec " + run["spec"]["spec_hash"] in text
    assert "No changes after the first look are recorded" in text
    assert "left uncorrected" not in text                                         # old disclosure only appears next to the review it refers to


def test_placebo_reports_how_many_distinct_lags_it_used(tmp_path):
    prices, ix, uni, q, s = synthetic()
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "r", META)
    lags = run["results"]["shift_lags"].dropna()
    assert len(lags) and (lags >= 1).all() and (lags <= 2 * (400 - 70 + 1)).all()
    assert "shift_lags" in pd.read_csv(tmp_path / "r" / "results.csv").columns


def test_missing_tickers_in_the_spec_are_named_and_counted(tmp_path):
    prices, ix, uni, q, s = synthetic()
    dropped = uni[-1].ticker
    prices.pop(dropped)
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "r", {**META, "missing_tickers": [dropped]})
    text = render_report(run, s, CH)
    assert f"{len(prices)} of {len(uni)} stocks: {dropped} had no usable price data" in text


def test_unknown_hash_prints_no_review_and_never_inherits_old_text():
    from dipdash.backtest_notes import NOTES, REVIEWED_SPEC, notes_for, revisions_for
    assert notes_for("0123456789abcdef") == {} and revisions_for("0123456789abcdef") == []
    assert REVIEWED_SPEC in NOTES and NOTES[REVIEWED_SPEC]["review"]


def test_notes_for_a_known_hash_are_printed_with_the_not_acted_on_disclosure_and_the_quoted_primary_is_checked(tmp_path, monkeypatch):
    import dipdash.backtest_notes as bn
    prices, ix, uni, q, s = synthetic(effect=0.006)
    run0 = run_backtest(prices, ix, uni, q, s, tmp_path / "a", META)
    h = run0["spec"]["spec_hash"]
    prim = run0["results"].query("variant == 'V1_price_only' and horizon == 21 and group == 'All' and period == 'OOS'").iloc[0]
    notes = {h: {"revisions": ["Test revision one.", "Test revision two NOT acted on."], "review": "Test review text.",
                 "data_notes": ["Test data note."], "quoted": {"primary_ex_own": float(prim["ex_own"]), "primary_n": int(prim["n"])}}}
    monkeypatch.setattr(bn, "NOTES", notes)
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "b", META)
    assert run["spec"]["spec_hash"] == h and run["spec"]["revisions_after_first_look"] == notes[h]["revisions"]
    run["primary_history"] = [{"run_at": "x", "spec_hash": h, "n": int(prim["n"]), "ex_own": float(prim["ex_own"])}] * 2
    text = render_report(run, s, CH)
    assert "Test review text." in text and "Test revision two NOT acted on." in text and "left uncorrected" in text
    assert "identical in every logged run" in text and f"{float(prim['ex_own']):+.4%}" in text
    assert "**Note: figures differ.**" not in text                                      # quoted figure agrees with the run
    notes[h]["quoted"] = {"primary_ex_own": float(prim["ex_own"]) + 0.01, "primary_n": int(prim["n"])}
    mism = render_report(run, s, CH)
    assert "**Note: figures differ.** The recorded notes quote a result for the main question" in mism and "**Check:**" not in mism
    run["primary_history"][1] = {**run["primary_history"][0], "n": int(prim["n"]) + 1}
    assert "identical in every logged run" not in render_report(run, s, CH)


def test_earlier_spec_hashes_in_the_trial_log_are_always_mentioned(tmp_path):
    from dipdash.backtest_report import earlier_specs_line
    assert earlier_specs_line([], "h1") == "" and earlier_specs_line([{"spec_hash": "h1"}], "h1") == ""
    line = earlier_specs_line([{"spec_hash": "old1"}, {"spec_hash": "old1"}, {"spec_hash": "old2"}, {"spec_hash": "h1"}], "h1")
    assert "2 earlier spec hashes" in line and "old1" in line and "old2" in line
    prices, ix, uni, q, s = synthetic()
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "r", META)
    assert run["spec"]["revisions_after_first_look"] == []                              # no notes for this hash
    run["primary_history"] = [{"run_at": "x", "spec_hash": "oldhash", "n": 3, "ex_own": 0.01}]
    text = render_report(run, s, CH)
    assert "earlier spec hash" in text and "oldhash" in text                            # shown even without notes for the current hash
    assert "No changes after the first look are recorded" in text


def test_editing_a_note_does_not_change_the_spec_hash(monkeypatch):
    import dipdash.backtest_notes as bn
    prices, ix, uni, q, s = synthetic()
    cal = sorted({d for c in prices.values() for d in c.index})
    h = freeze_spec(s, uni, META, cal)["spec_hash"]
    monkeypatch.setattr(bn, "NOTES", {h: {"revisions": ["a"]}})
    a = freeze_spec(s, uni, META, cal)
    monkeypatch.setattr(bn, "NOTES", {h: {"revisions": ["a", "b", "an edited note"], "review": "changed"}})
    b = freeze_spec(s, uni, META, cal)
    assert a["spec_hash"] == b["spec_hash"] == h and a["revisions_after_first_look"] != b["revisions_after_first_look"]


def test_the_recorded_notes_quote_the_published_sample_run():
    """The review text in backtest_notes quotes +0.2660% and n = 1,504; they must agree with the committed sample results."""
    from pathlib import Path
    from dipdash.backtest_notes import NOTES, REVIEWED_SPEC
    sample = Path(__file__).resolve().parents[1] / "docs" / "sample-output" / "backtest"
    if not (sample / "results.csv").exists() or json.loads((sample / "spec.json").read_text())["spec_hash"] != REVIEWED_SPEC:
        pytest.skip("sample output for the reviewed spec is not present")
    r = pd.read_csv(sample / "results.csv").query("variant == 'V1_price_only' and horizon == 21 and group == 'All' and period == 'OOS'").iloc[0]
    q = NOTES[REVIEWED_SPEC]["quoted"]
    assert int(r["n"]) == q["primary_n"] and r["ex_own"] == pytest.approx(q["primary_ex_own"], abs=5e-7)
    assert f"{q['primary_ex_own']:+.4%}" in NOTES[REVIEWED_SPEC]["review"]
