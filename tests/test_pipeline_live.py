"""DATA-1 half 2: the live branch of cli.main, run offline on tests/fakes.FakeYahoo. An autouse tripwire makes
`import yfinance` / `import openbb` fail, so any real network call errors loudly. Dates are frozen to the Friday after synth.END."""
import csv
import sys
from datetime import date

import pytest

from dipdash import cli
from dipdash.config import load_settings
from fakes import FakeYahoo
from synth import geometric

TODAY = date(2026, 10, 30)
US = [f"US{i}" for i in range(28)]
ALL = US + ["SEB.ST", "NDA.HE"]
INDICES = tuple(i.symbol for i in load_settings().all_indices)


class _Date(date):
    @classmethod
    def today(cls):
        return TODAY


@pytest.fixture(autouse=True)
def frozen_and_offline(monkeypatch):
    monkeypatch.setattr(cli, "date", _Date)
    monkeypatch.setitem(sys.modules, "yfinance", None)
    monkeypatch.setitem(sys.modules, "openbb", None)


@pytest.fixture
def env(tmp_path):
    uni = tmp_path / "universe.csv"
    rows = [(t, t, "US") for t in US] + [("SEB.ST", "SEB", "Europe"), ("NDA.HE", "Nordea", "Europe")]
    uni.write_text("ticker,name,region\n" + "\n".join(",".join(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path, uni


def make_fake(**kw) -> FakeYahoo:
    prices = {t: geometric(300, 0.0005 + 0.0001 * i) for i, t in enumerate(ALL)}
    kw.setdefault("fx", {"SEK": 0.095, "EUR": 1.08})
    kw.setdefault("index", {s: geometric(300, 0.0003) for s in INDICES})
    return FakeYahoo(prices, **kw)


def run(env, fake, *extra, data="data"):
    tmp, uni = env
    argv = ["--universe", str(uni), "--out", str(tmp / "output" / "dashboard.html"), "--data-dir", str(tmp / data),
            "--no-crosscheck", *extra]
    return cli.main(argv, sources=fake.sources())


def quality(tmp, name="data_quality.csv"):
    with (tmp / "output" / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def checks(rows):
    return {(r["ticker"], r["check"]): r for r in rows}


def test_happy_path_writes_every_artifact(env):
    tmp, _ = env
    fake = make_fake()
    assert run(env, fake) == 0
    out = tmp / "output"
    assert (out / "dashboard.html").stat().st_size > 0 and (out / "digest.md").stat().st_size > 0
    assert (out / "data_quality.csv").exists() and not (out / "data_quality.failed.csv").exists()
    raw = list((tmp / "data" / "raw").glob("yfinance*"))
    assert any(p.name.startswith("yfinance") and "openbb" not in p.name for p in raw)
    assert not list((tmp / "data" / "raw").glob("openbb_fallback*"))
    assert (tmp / "data" / "fundamentals.json").exists()
    kinds = {k for k, _ in fake.calls}
    assert {"prices", "fx", "index", "info", "earnings"} <= kinds and "fallback" not in kinds
    assert "SEB.ST" in (out / "dashboard.html").read_text(encoding="utf-8")


def test_primary_failure_uses_fallback_and_logs_price_source(env):
    tmp, _ = env
    fake = make_fake(fail={"US3"}, fallback={"US3": geometric(300, 0.0004)})
    assert run(env, fake) == 0
    assert list((tmp / "data" / "raw").glob("openbb_fallback*"))
    got = checks(quality(tmp))
    assert got[("US3", "price_source")]["severity"] == "warn" and "unadjusted" in got[("US3", "price_source")]["detail"]
    assert "US3" in fake.called("fallback")


def test_lag_nan_tail_and_failed_ticker_show_up_with_severity_and_detail(env):
    tmp, _ = env
    fake = make_fake(lag={"US1": 6}, nan_tail={"US2": 2}, fail={"US4"})       # US4: no fallback bars either
    assert run(env, fake) == 0                                                 # 27 of 30 screened = exactly the minimum
    got = checks(quality(tmp))
    assert got[("US1", "stale")]["severity"] == "error" and "older than" in got[("US1", "stale")]["detail"]
    assert ("US2", "stale") not in got                                         # a NaN tail is judged on its last real bar
    assert "US4" not in {t for t, c in got if c == "price_source"}


def test_index_missing_and_fx_missing_do_not_crash(env):
    tmp, _ = env
    fake = make_fake(index={s: geometric(300, 0.0003) for s in INDICES if s != "^OMXH25"}, fx={"SEK": 0.095})   # EUR pair absent
    assert run(env, fake) == 0
    got = checks(quality(tmp))
    miss = [r for (t, c), r in got.items() if c == "index_missing"]
    assert len(miss) == 1 and "^OMXH25" in miss[0]["detail"] and miss[0]["severity"] == "warn"
    assert "NDA.HE" in (tmp / "output" / "dashboard.html").read_text(encoding="utf-8")


def test_too_few_screened_returns_2_and_keeps_yesterdays_files(env):
    tmp, _ = env
    assert run(env, make_fake()) == 0
    out = tmp / "output"
    before = {n: (out / n).read_bytes() for n in ("dashboard.html", "digest.md", "data_quality.csv")}
    bad = make_fake(fail=set(ALL[:10]))                                          # a third of the universe has no data at all
    assert run(env, bad) == 2
    assert {n: (out / n).read_bytes() for n in before} == before
    failed = quality(tmp, "data_quality.failed.csv")
    assert failed and all(set(r) >= {"ticker", "check", "severity", "detail"} for r in failed)


def test_later_good_run_removes_failed_note(env):
    tmp, _ = env
    assert run(env, make_fake(fail=set(ALL[:10]))) == 2
    assert (tmp / "output" / "data_quality.failed.csv").exists() and not (tmp / "output" / "dashboard.html").exists()
    assert run(env, make_fake(), data="data2") == 0       # own data dir: raw fundamentals files are named to the second and would collide
    assert not (tmp / "output" / "data_quality.failed.csv").exists()


def test_batch_download_raising_exits_2_and_keeps_files(env):
    tmp, _ = env
    assert run(env, make_fake()) == 0
    before = (tmp / "output" / "dashboard.html").read_bytes()
    assert run(env, make_fake(down=True), data="data2") == 2
    assert (tmp / "output" / "dashboard.html").read_bytes() == before
    rows = quality(tmp, "data_quality.failed.csv")
    assert rows[0]["check"] == "price_source" and "network unreachable" in rows[0]["detail"]


def test_demo_run_never_touches_the_real_quality_log(env):
    tmp, uni = env
    assert run(env, make_fake()) == 0
    log = (tmp / "output" / "data_quality.csv").read_bytes()
    assert cli.main(["--demo", "--out", str(tmp / "output" / "dashboard.html"), "--data-dir", str(tmp / "data")]) == 0
    assert (tmp / "output" / "data_quality.csv").read_bytes() == log
    assert (tmp / "output" / "data_quality.demo.csv").exists()


def test_crosscheck_uses_the_bundle_and_says_when_openbb_is_missing(env, capsys):
    tmp, uni = env
    argv = ["--universe", str(uni), "--out", str(tmp / "output" / "dashboard.html"), "--data-dir", str(tmp / "data")]
    assert cli.main(argv, sources=make_fake().sources()) == 0
    assert "Cross-check skipped: OpenBB is not installed" in capsys.readouterr().out


def test_no_bundle_and_no_yfinance_exits_with_install_hint(env):
    tmp, uni = env
    with pytest.raises(SystemExit) as e:
        cli.main(["--universe", str(uni), "--out", str(tmp / "o" / "d.html"), "--data-dir", str(tmp / "data")])
    assert "yfinance is not installed" in str(e.value)


# --- forward ledger (RES-5): the hook records only default-rule live runs ---------------------------------------------

@pytest.fixture
def default_cfg(env, monkeypatch):
    """A config folder under tmp_path, so a run WITHOUT --universe/--settings (the only kind that is recorded) stays offline."""
    import shutil

    from dipdash import config
    tmp, uni = env
    cfg = tmp / "config"
    cfg.mkdir()
    shutil.copy(uni, cfg / "universe.csv")
    shutil.copy(config.CONFIG_DIR / "settings.toml", cfg / "settings.toml")
    monkeypatch.setattr(config, "CONFIG_DIR", cfg)
    monkeypatch.setattr(cli, "CONFIG_DIR", cfg)
    return tmp


def run_default(tmp, fake, *extra):
    argv = ["--out", str(tmp / "output" / "dashboard.html"), "--data-dir", str(tmp / "data"), "--no-crosscheck", *extra]
    return cli.main(argv, sources=fake.sources())


def test_live_run_records_the_ledger(default_cfg):
    tmp = default_cfg
    assert run_default(tmp, make_fake()) == 0
    import hashlib

    import pandas as pd
    flags = tmp / "data" / "ledger" / "flags.csv"
    led = pd.read_csv(flags, dtype=str)
    assert set(led["ticker"]) == set(ALL) and led["asof"].nunique() == 1
    assert set(led["universe_hash"]) == {hashlib.sha256((tmp / "config" / "universe.csv").read_bytes().replace(b"\r\n", b"\n")).hexdigest()}
    assert led["code_hash"].str.len().eq(64).all() and set(led["schema_version"]) == {"1"}
    assert len(list((tmp / "data" / "ledger" / "versions").iterdir())) == 2 and (tmp / "data" / "ledger" / "runs.csv").exists()
    before = flags.read_bytes()
    assert run_default(tmp, make_fake()) == 0                           # a second run on the same data adds nothing
    assert flags.read_bytes() == before and (tmp / "data" / "ledger" / "flags.backup.csv").read_bytes() == before


def test_custom_universe_or_settings_is_not_recorded(env, capsys):
    tmp, uni = env
    assert run(env, make_fake()) == 0                                   # run() passes --universe
    assert not (tmp / "data" / "ledger").exists() and "Ledger skipped" in capsys.readouterr().out


def test_custom_settings_is_not_recorded(default_cfg, capsys):
    tmp = default_cfg
    assert run_default(tmp, make_fake(), "--settings", str(tmp / "config" / "settings.toml")) == 0
    assert not (tmp / "data" / "ledger").exists() and "Ledger skipped" in capsys.readouterr().out


def test_demo_run_writes_no_ledger(env):
    tmp, _ = env
    assert cli.main(["--demo", "--out", str(tmp / "output" / "dashboard.html"), "--data-dir", str(tmp / "data")]) == 0
    assert not (tmp / "data" / "ledger").exists()


def test_locked_ledger_keeps_exit_code_page_and_warns_in_the_quality_log(default_cfg, capsys):
    tmp = default_cfg
    (tmp / "data" / "ledger" / "flags.csv").mkdir(parents=True)         # a directory where the file should be: cannot be opened
    assert run_default(tmp, make_fake()) == 0
    assert (tmp / "output" / "dashboard.html").stat().st_size > 0 and (tmp / "output" / "run_meta.json").exists()
    assert "Ledger not updated" in capsys.readouterr().out
    assert (tmp / "data" / "ledger" / "flags.csv").is_dir()             # nothing was replaced
    hit = [r for r in quality(tmp) if r["check"] == "ledger_not_updated"]
    assert len(hit) == 1 and hit[0]["severity"] == "warn"


def test_ledger_failure_by_exception_keeps_exit_code(default_cfg, capsys, monkeypatch):
    tmp = default_cfg
    from dipdash import ledger

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ledger, "append_rows", boom)
    assert run_default(tmp, make_fake()) == 0
    assert "Ledger not updated" in capsys.readouterr().out
    assert any(r["check"] == "ledger_not_updated" for r in quality(tmp))


class _Clock:
    """Stands in for cli.datetime: now() returns the next time in the list, then keeps the last one."""
    def __init__(self, *times):
        self.times = list(times)

    def __call__(self, real):
        clock = self

        class Fake(real):
            @classmethod
            def now(cls, tz=None):
                return clock.times.pop(0) if len(clock.times) > 1 else clock.times[0]
        return Fake


def test_a_partial_bar_goes_through_the_cli_but_not_into_the_ledger(default_cfg, monkeypatch):
    import pandas as pd
    from datetime import datetime as real_dt, timezone
    tmp = default_cfg
    monkeypatch.setattr(cli, "datetime", _Clock(real_dt(2026, 10, 30, 12, 0, tzinfo=timezone.utc))(real_dt))
    prices = {t: geometric(300, 0.0005 + 0.0001 * i) for i, t in enumerate(ALL)}
    prices["US0"] = geometric(300, 0.0005, end="2026-10-30")             # this bar is dated today and the US market is still open
    fake = FakeYahoo(prices, fx={"SEK": 0.095, "EUR": 1.08}, index={s: geometric(300, 0.0003) for s in INDICES})
    assert run_default(tmp, fake) == 0
    led = pd.read_csv(tmp / "data" / "ledger" / "flags.csv", dtype=str)
    assert "US0" not in set(led["ticker"]) and len(led) == len(ALL) - 1
    runs = pd.read_csv(tmp / "data" / "ledger" / "runs.csv", dtype=str)
    assert runs["partial_count"].iloc[0] == "1" and '"US0":"partial"' in runs["skipped"].iloc[0]


def test_the_clock_is_read_before_the_prices_are_fetched(default_cfg, monkeypatch):
    """Price taken at 17:25 CET, validation done at 17:46 CET: the 17:46 reading would call a 17:30 close complete."""
    import pandas as pd
    from datetime import datetime as real_dt, timezone
    tmp = default_cfg
    first, later = real_dt(2026, 10, 30, 16, 25, tzinfo=timezone.utc), real_dt(2026, 10, 30, 16, 46, tzinfo=timezone.utc)
    monkeypatch.setattr(cli, "datetime", _Clock(first, later)(real_dt))
    prices = {t: geometric(300, 0.0005 + 0.0001 * i, end="2026-10-30") for i, t in enumerate(ALL)}
    fake = FakeYahoo(prices, fx={"SEK": 0.095, "EUR": 1.08}, index={s: geometric(300, 0.0003) for s in INDICES})
    assert run_default(tmp, fake) == 0
    flags = tmp / "data" / "ledger" / "flags.csv"
    assert not flags.exists() or pd.read_csv(flags).empty
    runs = pd.read_csv(tmp / "data" / "ledger" / "runs.csv", dtype=str)
    assert runs["rows_written"].iloc[0] == "0" and int(runs["partial_count"].iloc[0]) + int(runs["too_soon_count"].iloc[0]) == len(ALL)
