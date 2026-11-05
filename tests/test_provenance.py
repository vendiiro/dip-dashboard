"""provenance.py: code hash, package versions, per-section settings hashes; recorded in every spec but never hashed."""
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from dipdash import registry
from dipdash.config import Settings
from dipdash.provenance import build_provenance, code_hash, package_versions, settings_section_hashes

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dipdash"
S = Settings()


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_code_hash_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    (a / "m.py").write_bytes(b"x = 1\ny = 2\n")
    (b / "m.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    assert code_hash(a) == code_hash(b)


def test_code_hash_changes_with_the_code(tmp_path):
    (tmp_path / "m.py").write_text("x = 1\n")
    h1 = code_hash(tmp_path)
    (tmp_path / "m.py").write_text("x = 2\n")
    assert code_hash(tmp_path) != h1
    (tmp_path / "n.py").write_text("")                                      # a new file also changes it
    h2 = code_hash(tmp_path)
    (tmp_path / "n.py").unlink()
    assert code_hash(tmp_path) != h2


def test_section_hashes_isolate_a_news_edit():
    a, b = settings_section_hashes(S), settings_section_hashes(replace(S, news=replace(S.news, fetch_if_5d_drop=.5)))
    assert a["news"] != b["news"] and a["dip"] == b["dip"] and a["backtest"] == b["backtest"]
    assert a["quality"] == b["quality"]                                     # quality holds dicts: must still hash


def test_section_hashes_treat_tuples_and_lists_alike():
    s2 = replace(S, quality=replace(S.quality, not_applicable={k: list(v) for k, v in S.quality.not_applicable.items()}))
    assert settings_section_hashes(S)["quality"] == settings_section_hashes(s2)["quality"]


def test_package_versions_names_missing_packages_as_none():
    v = package_versions(("pandas", "no_such_package_xyz"))
    assert v["pandas"] == pd.__version__ and v["no_such_package_xyz"] is None


def test_provenance_never_changes_the_spec_hash():
    spec = {"a": 1}
    prov = {"provenance": {"code": "x"}}
    assert registry.spec_hash({**spec, **prov}) == registry.spec_hash(spec)
    assert registry.hash_for("features", {**spec, **prov}) == registry.hash_for("features", spec)
    assert registry.hash_for("backtest", {**spec, **prov}) == registry.hash_for("backtest", spec)


def test_build_provenance_has_code_packages_and_settings():
    p = build_provenance(S, SRC)
    assert set(p) >= {"code_sha256", "packages", "settings_sections"}
    assert p["settings_sections"]["news"] and "pandas" in p["packages"]


def test_data_meta_has_no_whole_file_settings_hash(tmp_path):
    mod = _load_script("run_backtest")
    raw = tmp_path / "raw.csv.gz"
    raw.write_bytes(b"x")
    c = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    meta = mod.build_data_meta(raw, "2023-01-01", {"A": c}, {}, [], {"US": c})
    assert "settings_sha256" not in meta and meta["raw_file"] == "raw.csv.gz" and "universe_sha256" in meta


def test_backtest_archive_holds_provenance_but_the_hash_ignores_it(tmp_path):
    from test_backtest_run import META, synthetic
    from dipdash.backtest_run import freeze_spec, run_backtest
    prices, ix, uni, q, s = synthetic(n_stocks=6)
    run = run_backtest(prices, ix, uni, q, s, tmp_path / "out", META)
    spec = run["spec"]
    assert "provenance" in spec and "settings_sha256" not in spec["data"]
    archived = json.loads(next((tmp_path / "out").glob("spec_*.json")).read_text())
    assert "provenance" in archived and archived["provenance"]["code_sha256"]
    cal = sorted({d for c in prices.values() for d in c.index if d >= pd.Timestamp(s.backtest.start_date)})
    assert registry.hash_for("backtest", archived) == freeze_spec(s, uni, META, cal)["spec_hash"] == spec["spec_hash"]


def test_feature_runner_writes_provenance_and_no_settings_sha(tmp_path, monkeypatch):
    from test_feature_experiment import _synthetic_raw
    mod = _load_script("run_feature_experiment")
    raw, uni, s = _synthetic_raw(tmp_path)
    monkeypatch.setattr(mod, "load_universe", lambda: uni)
    monkeypatch.setattr(mod, "load_settings", lambda: s)
    root = tmp_path / "out"
    assert mod.main(["--raw", str(raw), "--out-root", str(root), "--draws", "50"]) == 0
    for f in (next(root.glob("*_features/spec_features.json")), next(root.glob("*_features/spec_[0-9a-f]*.json"))):
        spec = json.loads(f.read_text())
        assert spec["provenance"]["code_sha256"] and "settings_sha256" not in spec["parent_backtest_spec"]
        assert spec["spec_hash"] == registry.hash_for("features", spec)


def test_forecast_spec_gets_provenance_before_registration(tmp_path):
    mod = _load_script("run_forecast_calibration")
    raw = tmp_path / "raw.csv.gz"
    raw.write_bytes(b"x")
    spec = mod.forecast_spec(raw, ["A", "B"], pd.Timestamp("2022-01-03"), 0, "forecast_t", S)
    h = spec["spec_hash"]
    mod.attach_provenance(spec, S)
    assert spec["provenance"]["code_sha256"] and registry.hash_for("forecast", spec) == h
    reg = registry.register("forecast", spec, tmp_path / "o", tmp_path / "root",
                            fields={"oos_start": "2022-02-01", "oos_end": "2022-12-30"})
    archived = json.loads(reg.spec_file.read_text())
    assert archived["provenance"] == spec["provenance"]


# ---------------------------------------------------------------- converse: every setting a runner uses moves the spec hash
class _Stop(Exception):
    pass


def _stop(*a, **k):
    raise _Stop()


def _bump(v):
    if isinstance(v, tuple):
        return v + (v[-1] + 1,)
    return v + 1 if isinstance(v, int) else v * 1.5 + 0.01


BACKTEST_FIELDS = {"dip": ["drop_1d", "drop_5d", "drawdown_20d"],
                   "backtest": ["horizons", "cooldown_days", "cost_roundtrip", "oos_fraction", "stress_drawdown", "stress_window",
                                "bootstrap_draws", "ci_level", "placebo_draws", "seed"]}


def test_every_backtest_setting_the_computation_uses_moves_the_spec_hash():
    from test_backtest_run import META, synthetic
    from dataclasses import fields
    from dipdash.backtest_run import freeze_spec
    prices, ix, uni, q, s = synthetic(n_stocks=4)
    cal = sorted({d for c in prices.values() for d in c.index if d >= pd.Timestamp(s.backtest.start_date)})
    h = freeze_spec(s, uni, META, cal)["spec_hash"]
    names = {"dip": BACKTEST_FIELDS["dip"], "falling_knife": [f.name for f in fields(s.falling_knife)], "backtest": BACKTEST_FIELDS["backtest"]}
    for sec, flds in names.items():
        for f in flds:
            sub = getattr(s, sec)
            s2 = replace(s, **{sec: replace(sub, **{f: _bump(getattr(sub, f))})})
            assert freeze_spec(s2, uni, META, cal)["spec_hash"] != h, f"{sec}.{f} does not move the backtest spec hash"


def test_backtest_start_date_moves_the_hash_through_history_from(tmp_path):
    mod = _load_script("run_backtest")
    raw = tmp_path / "raw.csv.gz"
    raw.write_bytes(b"x")
    c = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    a = mod.build_data_meta(raw, "2023-01-01", {"A": c}, {}, [], {"US": c})
    b = mod.build_data_meta(raw, "2022-01-01", {"A": c}, {}, [], {"US": c})
    assert registry.spec_hash({"data": a}) != registry.spec_hash({"data": b})


def test_data_meta_records_the_fundamentals_file_hash(tmp_path):
    mod = _load_script("run_backtest")
    raw, fund = tmp_path / "raw.csv.gz", tmp_path / "fundamentals.json"
    raw.write_bytes(b"x")
    fund.write_text("{}")
    c = pd.Series([1.0], index=pd.to_datetime(["2024-01-02"]))
    m = mod.build_data_meta(raw, "2023-01-01", {"A": c}, {}, [], {"US": c}, fund)
    assert len(m["fundamentals_sha256"]) == 64


def test_provenance_records_the_python_version():
    import platform
    assert build_provenance(S, SRC)["python"] == platform.python_version()


def test_every_features_setting_the_computation_uses_moves_the_spec_hash(tmp_path, monkeypatch):
    from dataclasses import fields
    from test_feature_experiment import _synthetic_raw
    mod = _load_script("run_feature_experiment")
    raw, uni, s = _synthetic_raw(tmp_path)
    monkeypatch.setattr(mod, "load_universe", lambda: uni)
    n = [0]

    def run(s2):
        n[0] += 1
        monkeypatch.setattr(mod, "load_settings", lambda: s2)
        monkeypatch.setattr(mod, "build_event_table", _stop)   # spec only, no compute
        root = tmp_path / f"o{n[0]}"
        try:
            mod.main(["--raw", str(raw), "--out-root", str(root)])
        except _Stop:
            pass
        return json.loads(next(root.glob("*_features/spec_features.json")).read_text())["spec_hash"]

    h = run(s)
    start = str((pd.Timestamp(s.backtest.start_date) + pd.Timedelta(days=30)).date())
    cases = [("dip", f) for f in ("drop_1d", "drop_5d", "drawdown_20d")] + [("falling_knife", f.name) for f in fields(s.falling_knife)]
    cases += [("backtest", f) for f in ("horizons", "cooldown_days", "oos_fraction", "bootstrap_draws", "ci_level", "seed")]
    for sec, f in cases:
        sub = getattr(s, sec)
        s2 = replace(s, **{sec: replace(sub, **{f: _bump(getattr(sub, f))})})
        assert run(s2) != h, f"{sec}.{f} does not move the features spec hash"
    assert run(replace(s, backtest=replace(s.backtest, start_date=start))) != h, "backtest.start_date does not move the features spec hash"


def test_features_freeze_spec_without_a_rule_keeps_its_hash():
    from dipdash.feature_experiment import freeze_spec as ff
    base = ff({"spec_hash": "p"}, "2024-01-01", 5, "f", {"draws": 1})
    assert ff({"spec_hash": "p"}, "2024-01-01", 5, "f", {"draws": 1}, None)["spec_hash"] == base["spec_hash"]
    assert ff({"spec_hash": "p"}, "2024-01-01", 5, "f", {"draws": 1}, {"dip": {}})["spec_hash"] != base["spec_hash"]
