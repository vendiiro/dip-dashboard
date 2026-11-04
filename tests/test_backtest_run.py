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
    assert len(spec["revisions_after_first_look"]) >= 3
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
