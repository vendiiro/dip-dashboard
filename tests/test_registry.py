"""registry.py: one hash (pinned), required fields, never-overwrite, token-gated trial log, period ledger, one-off backfill."""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from dipdash import feature_experiment as fe
from dipdash import registry
from dipdash.registry import Registration, RegistrationError

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "docs" / "sample-output" / "backtest" / "spec.json"


def spec(**over) -> dict:
    """A minimal forecast-kind spec holding every field the registry reads from a forecast spec."""
    s = {"family_id": "forecast_t", "criterion_text": "coverage within 0.80 +/- 0.04", "verdict_rule": {"text": "pass if both within"},
         "split": {"cutoff": "2020-12-31"}, "design": {"horizons": [21]}, "planned_cells": 4, "data": {"raw_sha256": "ab" * 32},
         "notes": "descriptive"}
    s.update(over)
    return s


WIN = {"oos_start": "2021-01-04", "oos_end": "2021-12-31"}


def rows(n=4, **over):
    return pd.DataFrame([{"cell": f"m{i}", "stat": "coverage", "group": "ALL OOS", "period": "OOS", "horizon": 21, "n": 10,
                          "estimate": 0.8, "lo": 0.7, "hi": 0.9, "primary": i == 0, **over} for i in range(n)])


# ---------------------------------------------------------------- hash (golden)
def test_golden_hashes_of_existing_specs_do_not_change():
    from test_backtest_run import META, synthetic
    from dipdash.backtest_run import freeze_spec
    prices, ix, uni, q, s = synthetic()
    cal = sorted({d for c in prices.values() for d in c.index})
    assert freeze_spec(s, uni, META, cal)["spec_hash"] == "e1687cf9f8045f73"           # synthetic backtest spec, pinned before RES-4
    f = fe.freeze_spec({"spec_hash": "8583ea959c7ce228", "raw_file": "x.csv.gz", "raw_sha256": "0" * 64}, "2019-06-28", 171,
                       "features_2026-11-04", {"draws": 5000, "level": 0.9, "seed": 2101})
    assert f["spec_hash"] == "89ee3793566eb8a5" == fe.spec_hash(f)                      # features spec, pinned before RES-4
    assert registry.spec_hash({"a": 1}) == "f9d86028c6e0d64e"                            # sha256(b"{\"a\": 1}")[:16], the function itself


def test_the_published_sample_spec_still_hashes_to_its_recorded_value():
    if not SAMPLE.exists():
        pytest.skip("sample spec not present")
    s = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert s["spec_hash"] == "79288caaa97d33b1" == registry.hash_for("backtest", s)
    assert registry.hash_for("backtest", {**s, "registration": {"oos_reuse": ["x"]}, "sample_notes": "edited"}) == s["spec_hash"]
    assert registry.hash_for("backtest", {**s, "horizons": [5]}) != s["spec_hash"]


def test_excluded_keys_are_per_kind():
    s = spec()
    assert registry.hash_for("forecast", s) == registry.hash_for("forecast", {**s, "notes": "changed"})
    assert registry.hash_for("backtest", s) != registry.hash_for("backtest", {**s, "notes": "changed"})   # not a backtest notes key
    with pytest.raises(RegistrationError):
        registry.hash_for("other", s)


# ---------------------------------------------------------------- register
def test_required_fields_are_checked_and_named(tmp_path):
    s = spec()
    del s["criterion_text"]
    with pytest.raises(RegistrationError, match="hypothesis"):
        registry.register("forecast", s, tmp_path / "r", tmp_path, WIN)
    with pytest.raises(RegistrationError, match="oos_start, oos_end"):
        registry.register("forecast", spec(), tmp_path / "r", tmp_path, {})
    with pytest.raises(RegistrationError, match="must start after"):
        registry.register("forecast", spec(), tmp_path / "r", tmp_path, {"oos_start": "2020-06-01", "oos_end": "2021-01-01"})
    with pytest.raises(RegistrationError, match="the runner says"):                     # spec and runner disagree
        registry.register("forecast", spec(), tmp_path / "r", tmp_path, {**WIN, "planned_cells": 5})
    with pytest.raises(RegistrationError, match="hashes to"):
        registry.register("forecast", {**spec(), "spec_hash": "0" * 16}, tmp_path / "r", tmp_path, WIN)
    assert not (tmp_path / "registry.csv").exists()                                      # nothing written on a refused registration


def test_register_writes_the_spec_once_and_appends_a_row_each_time(tmp_path):
    a = registry.register("forecast", spec(), tmp_path / "r", tmp_path, WIN)
    f = tmp_path / "r" / f"spec_{a.spec_hash}.json"
    first = f.read_text()
    assert json.loads(first)["registration"]["oos_start"] == "2021-01-04"
    b = registry.register("forecast", spec(notes="edited"), tmp_path / "r", tmp_path, WIN)
    assert b.spec_hash == a.spec_hash and f.read_text() == first                         # never overwritten
    reg = registry.read_registry(tmp_path)
    assert list(reg.columns) == registry.REGISTRY_COLS and len(reg) == 2
    assert reg.iloc[0][["kind", "family_id", "oos_start", "oos_end", "horizons", "planned_cells", "source"]].tolist() == \
        ["forecast", "forecast_t", "2021-01-04", "2021-12-31", "21", "4", "registered"]


# ---------------------------------------------------------------- record_trials
def test_record_trials_requires_a_token_from_register(tmp_path):
    reg = registry.register("forecast", spec(), tmp_path / "r", tmp_path, WIN)
    forged = Registration("forecast", "forecast_t", reg.spec_hash, reg.registered_at, tmp_path, reg.spec_file, 4, "a", "b",
                          _token="0" * 32)
    for bad in (None, {"spec_hash": reg.spec_hash}, forged):
        with pytest.raises(RegistrationError, match="register"):
            registry.record_trials(bad, rows())
    (tmp_path / "r" / f"spec_{reg.spec_hash}.json").unlink()                             # the spec file must still exist
    with pytest.raises(RegistrationError):
        registry.record_trials(reg, rows())
    assert not (tmp_path / "trials_all.csv").exists()


def test_record_trials_refuses_another_spec_hash_and_unplanned_cells(tmp_path):
    reg = registry.register("forecast", spec(), tmp_path / "r", tmp_path, WIN)
    with pytest.raises(RegistrationError, match="spec_hash"):
        registry.record_trials(reg, rows(spec_hash="ffffffffffffffff"))
    with pytest.raises(RegistrationError, match="planned"):
        registry.record_trials(reg, rows(5))
    assert registry.record_trials(reg, rows(3)) == 3
    with pytest.raises(RegistrationError, match="planned"):                              # the limit is per registration, across calls
        registry.record_trials(reg, rows(2))
    log = registry.read_trials(tmp_path)
    assert list(log.columns) == registry.TRIAL_COLS and len(log) == 3 and log["primary"].sum() == 1
    assert set(log["spec_hash"]) == {reg.spec_hash} and set(log["kind"]) == {"forecast"}


def test_a_trial_log_with_another_layout_is_set_aside(tmp_path):
    (tmp_path / "trials_all.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    reg = registry.register("forecast", spec(), tmp_path / "r", tmp_path, WIN)
    registry.record_trials(reg, rows())
    assert len(registry.read_trials(tmp_path)) == 4
    assert [p.read_text() for p in tmp_path.glob("trials_all_older_layout_*.csv")] == ["a,b\n1,2\n"]


# ---------------------------------------------------------------- period ledger
def test_periods_viewed_finds_overlaps_across_kinds_and_treats_unknown_windows_as_overlapping(tmp_path):
    registry.register("forecast", spec(), tmp_path / "r", tmp_path, WIN)
    registry._append_registry(tmp_path, {"registered_at": "2026-01-01 00:00:00", "kind": "backtest", "spec_hash": "bt00000000000000",
                                         "source": "registered", "oos_start": "2022-01-03", "oos_end": "2022-06-30"})
    registry._append_registry(tmp_path, {"registered_at": "2025-01-01 00:00:00", "kind": "backtest", "spec_hash": "old0000000000000",
                                         "source": "backfilled", "oos_start": "", "oos_end": ""})
    hit = registry.periods_viewed("2021-06-01", "2021-07-01", tmp_path)
    assert set(hit["spec_hash"]) == {registry.hash_for("forecast", spec()), "old0000000000000"}
    assert set(registry.periods_viewed("2021-12-31", "2022-01-03", tmp_path)["spec_hash"]) >= {"bt00000000000000"}   # touching ends overlap
    assert "bt00000000000000" not in set(registry.periods_viewed("2023-01-01", "2023-02-01", tmp_path)["spec_hash"])


def test_reuse_is_recorded_in_the_spec_and_returned_but_never_blocks(tmp_path):
    first = registry.register("forecast", spec(), tmp_path / "a", tmp_path, WIN)
    assert first.oos_reuse == () and "No earlier registration" in first.reuse_note()
    other = registry.register("forecast", spec(family_id="forecast_u"), tmp_path / "b", tmp_path,
                              {"oos_start": "2021-06-01", "oos_end": "2022-03-01"})
    assert first.spec_hash in other.reuse_note() and "not untouched" in other.reuse_note()
    saved = json.loads(other.spec_file.read_text())
    assert saved["registration"]["oos_reuse"] == list(other.oos_reuse)
    assert registry.hash_for("forecast", saved) == other.spec_hash
    again = registry.register("forecast", spec(), tmp_path / "c", tmp_path, WIN)
    assert "same spec was registered 1 time before" in again.reuse_note() and other.spec_hash in again.reuse_note()


def test_earlier_specs_is_scoped_by_kind_ordered_and_bounded(tmp_path):
    t0 = datetime(2026, 1, 1)
    a = registry.register("forecast", spec(), tmp_path / "a", tmp_path, WIN, now=t0)
    b = registry.register("forecast", spec(family_id="x"), tmp_path / "b", tmp_path, WIN, now=t0.replace(day=2))
    registry.register("forecast", spec(family_id="y"), tmp_path / "c", tmp_path, WIN, now=t0.replace(day=3))
    assert registry.earlier_specs("backtest", tmp_path) == []
    assert registry.earlier_specs("forecast", tmp_path, exclude=b.spec_hash, before=b.registered_at) == [a.spec_hash]
    assert len(registry.earlier_specs("forecast", tmp_path)) == 3


# ---------------------------------------------------------------- backfill
OLD_BT = ("run_at,spec_hash,variant,horizon,group,period,n,ex_own,ex_own_lo,ex_own_hi,primary\n"
          "2026-11-01 10:00,90205cfc6da3a007,V1_price_only,21,All,OOS,10,0.01,-0.01,0.03,True\n"
          "2026-11-02 07:49,79288caaa97d33b1,V1_price_only,21,All,OOS,12,0.002660,-0.001,0.006,True\n"
          "2026-11-02 07:49,79288caaa97d33b1,V1_price_only,5,All,IS,12,0.003,0.0,0.006,False\n")
OLD_FE = ("run_at,family_id,spec_hash,feature,stat,group,period,horizon,n,estimate,lo,hi,p_raw,p_holm,sign_is\n"
          "2026-11-04 09:00,features_2026-11-04,2190157755c9916b,f1_volume_ratio,spearman,All,OOS,21,400,0.01,-0.02,0.04,0.5,1.0,1\n"
          "2026-11-04 09:00,features_2026-11-04,2190157755c9916b,f1_volume_ratio,spearman,All,IS,21,400,0.02,,,,,1\n")


def test_backfill_imports_old_logs_once_marked_and_leaves_them_untouched(tmp_path):
    (tmp_path / "trials.csv").write_text(OLD_BT, encoding="utf-8")
    (tmp_path / "trials_features.csv").write_text(OLD_FE, encoding="utf-8")
    run = tmp_path / "2026-11-02"
    run.mkdir()
    (run / "spec.json").write_text(json.dumps({"spec_hash": "79288caaa97d33b1", "split": {"cutoff": "2019-06-28"}, "horizons": [5, 21, 63],
                                               "data": {"raw_sha256": "cd" * 32, "last_bar": "2026-10-30"}}), encoding="utf-8")
    log = registry.backfill(tmp_path)
    assert len(log) == 3 and all("marked backfilled" in x for x in log)
    reg = registry.read_registry(tmp_path)
    assert list(reg["spec_hash"]) == ["90205cfc6da3a007", "79288caaa97d33b1", "2190157755c9916b"]
    assert set(reg["source"]) == {"backfilled"} and reg["note"].str.contains("registered after its results were seen").all()
    r = reg.set_index("spec_hash")
    assert r.loc["79288caaa97d33b1", ["oos_start", "oos_end", "split_cutoff"]].tolist() == ["2019-06-29", "2026-10-30", "2019-06-28"]
    assert r.loc["90205cfc6da3a007", "oos_start"] == ""                                 # spec file lost: window unknown
    t = registry.read_trials(tmp_path)
    assert len(t) == 5 and set(t["kind"]) == {"backtest", "features"}
    assert t[t["spec_hash"] == "79288caaa97d33b1"]["run_at"].tolist() == ["2026-11-02 07:49"] * 2      # original run times kept
    assert t[(t["kind"] == "features")]["primary"].tolist() == [True, False]
    assert (tmp_path / "trials.csv").read_text() == OLD_BT and (tmp_path / "trials_features.csv").read_text() == OLD_FE
    assert all(x.startswith("skip") for x in registry.backfill(tmp_path))                # idempotent
    assert len(registry.read_registry(tmp_path)) == 3 and len(registry.read_trials(tmp_path)) == 5
    # a backfilled spec with an unknown window is reported as possibly overlapping any new window
    new = registry.register("forecast", spec(), tmp_path / "n", tmp_path, WIN)
    assert "90205cfc6da3a007" in new.reuse_note() and "no recorded window" in new.reuse_note()
    assert registry.earlier_specs("backtest", tmp_path) == ["90205cfc6da3a007", "79288caaa97d33b1"]


def test_backfill_cli_runs(tmp_path, capsys):
    (tmp_path / "trials.csv").write_text(OLD_BT, encoding="utf-8")
    assert registry.main(["backfill", "--root", str(tmp_path)]) == 0
    assert "90205cfc6da3a007" in capsys.readouterr().out
