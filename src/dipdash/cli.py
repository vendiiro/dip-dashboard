"""Command line entry: python -m dipdash [--demo] [--out FILE] ..."""
from __future__ import annotations

import argparse
import math
import sys
import warnings
import webbrowser
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from .config import ROOT, load_settings, load_universe
from .dashboard import build_payload, write_dashboard
from .digest import build_digest, history_dates, latest_backtest_line
from .fsio import atomic_write_text
from .screen import needs_news


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="dipdash", description=__doc__)
    ap.add_argument("--demo", action="store_true", help="synthetic data, no network")
    ap.add_argument("--universe", help="CSV with columns ticker,name,region[,sector] (default config/universe.csv)")
    ap.add_argument("--settings", help="settings TOML (default config/settings.toml)")
    ap.add_argument("--out", default=str(ROOT / "output" / "dashboard.html"))
    ap.add_argument("--news-threshold", type=float, default=None,
                    help="fetch headlines for names down >= this over 5d (default from settings)")
    ap.add_argument("--no-crosscheck", action="store_true", help="skip the random cross-check against a second price source")
    ap.add_argument("--data-dir", default=str(ROOT / "data"), help="raw pulls and caches (default ./data)")
    ap.add_argument("--digest", help="where to write the daily digest (default: digest.md next to --out)")
    ap.add_argument("--history", action="store_true", help="also keep dated copies (by data date) of the dashboard, digest and data-quality log in history/ next to --out")
    ap.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    return ap


def _compress_old_history(history_dir: Path, today_asof: str, keep_days: int = 7) -> int:
    """gzip dated dashboards in history/ that are older than keep_days (each is about 3 MB of mostly repeated text).
    Digests and quality logs stay as they are (they are small and read by the next run). Raw price pulls are never touched.
    Returns how many files were compressed. A problem here must never fail the run."""
    import gzip
    import re
    from datetime import date as _date

    n = 0
    try:
        cutoff = _date.fromisoformat(today_asof).toordinal() - keep_days
        for p in sorted(history_dir.glob("dashboard_*.html")):
            m = re.fullmatch(r"dashboard_(\d{4}-\d{2}-\d{2})\.html", p.name)
            if not m or _date.fromisoformat(m.group(1)).toordinal() >= cutoff:
                continue
            gz = p.with_name(p.name + ".gz")
            tmp = gz.with_name(gz.name + ".tmp")
            with p.open("rb") as src, gzip.open(tmp, "wb", compresslevel=9) as dst:
                dst.write(src.read())
            tmp.replace(gz)
            p.unlink()
            n += 1
    except Exception as exc:
        print(f"history: could not compress old dashboards ({type(exc).__name__}: {exc})")
    return n


def _alerts(payload: dict, prices: dict, asof: str, out_path: Path, data_dir: Path, demo: bool, repeat: bool) -> list[dict] | None:
    """Trigger alerts for this run, or None if they could not be evaluated. A failure here never stops the dashboard.

    Evaluating a data date is idempotent: the first run for a date saves the state as it was before (alerts_state.pre.json), and
    any later run for the same date starts from that saved state again. So a mid-session run on partial bars followed by the
    post-close run ends with exactly what evaluating the final bars once would give, and nothing is shown or announced twice."""
    import json
    import shutil

    from .alerts import run_alerts, write_alerts_json

    tag = ".demo" if demo else ""                      # a demo run never touches the real alert state
    state_path = (out_path.parent if demo else data_dir) / f"alerts_state{tag}.json"
    pre_path = state_path.with_name(state_path.stem + ".pre.json")
    json_path = out_path.parent / f"alerts_latest{tag}.json"
    try:
        if state_path.exists():
            try:
                state_asof = json.loads(state_path.read_text(encoding="utf-8")).get("asof")
            except Exception:
                state_asof = None
            if state_asof == asof:                      # this date was evaluated before: start again from the state before it
                if pre_path.exists():
                    shutil.copyfile(pre_path, state_path)
                else:
                    state_path.unlink()                 # that evaluation was the very first run ever: start from scratch
            else:
                shutil.copyfile(state_path, pre_path)
        else:
            pre_path.unlink(missing_ok=True)
        earn = {r["t"]: r["earn"] for r in payload["rows"] if r.get("earn")}
        alerts, problem = run_alerts(payload["rows"], dict(prices), asof, state_path=state_path, earnings=earn, json_path=json_path)
        if problem:
            print(f"alerts: {problem}")
        return alerts
    except Exception as exc:
        print(f"alerts: could not be evaluated ({type(exc).__name__}: {exc})")
        try:                                            # never leave yesterday's file for the notifier to announce again
            json_path.write_text(json.dumps({"asof": asof, "count": 0, "alerts": [], "error": f"{type(exc).__name__}: {exc}"}), encoding="utf-8")
        except Exception:
            pass
        return None


def main(argv: list[str] | None = None) -> int:
    a = make_parser().parse_args(argv)
    settings = load_settings(a.settings)
    if a.news_threshold is not None:
        from dataclasses import replace
        settings = replace(settings, news=replace(settings.news, fetch_if_5d_drop=a.news_threshold))
    universe = load_universe(a.universe)
    tickers = [s.ticker for s in universe]

    today = date.today()
    data_dir = Path(a.data_dir)
    fx = None
    idx_hist: dict = {}      # full index close series for the beta fit; empty in demo mode
    earnings: dict = {}
    if a.demo:
        from .demo import demo_indices, demo_inputs, demo_news
        prices, funds = demo_inputs(universe)
        news_fn = demo_news
        indices = demo_indices(settings.indices)
        source: dict[str, str] = {}
    else:
        try:
            import yfinance  # noqa: F401
            # yfinance re-enables its own deprecation notices when imported, so this filter has to come after the import
            warnings.filterwarnings("ignore", module=r"yfinance(\.|$)")
        except ImportError:
            sys.exit("yfinance is not installed. Run: pip install -r requirements.txt")
        from . import openbb_source
        from .cache import save_raw_prices
        from .data import fetch_fundamentals, fetch_indices, fetch_news, fetch_prices, pull_prices
        from .fx import fetch_fx_to_usd

        print(f"Downloading 2y daily prices for {len(tickers)} tickers...")
        start = str(today - timedelta(days=730))
        prices, source = pull_prices(tickers, fetch_prices, lambda t: openbb_source.fetch_bars(t, start, str(today)))
        for src in ("primary", "fallback"):
            part = {t: v for t, v in prices.items() if source[t] == src}
            if part:
                path = save_raw_prices(part, "yfinance" if src == "primary" else "openbb_fallback", data_dir / "raw")
                print(f"  raw pull saved: {path}")
        funds = fetch_fundamentals(list(prices), data_dir / "fundamentals.json")
        fx = fetch_fx_to_usd(f.get("currency") for f in funds.values())
        indices = fetch_indices(settings.all_indices, history=idx_hist)
        from .earnings import load_earnings
        # Each stock is judged against ITS OWN last bar date: a US stock whose last bar is Tuesday must not be counted as if it
        # were Wednesday just because the European bars are already in. The cache is shared, so later groups fetch nothing new.
        by_date: dict = {}
        for t, v in prices.items():
            try:
                by_date.setdefault(v[0].dropna().index[-1].date(), []).append(t)
            except Exception:                           # an empty or odd series is skipped by the screen anyway
                continue
        for d, group in sorted(by_date.items()):
            try:
                earnings.update(load_earnings(group, data_dir / "earnings.json", d, settings.earnings,
                                              raw_dir=data_dir / "raw" / "yfinance_earnings"))
            except Exception as exc:                    # earnings are context; their failure must not stop the run
                print(f"earnings: skipped for {len(group)} stocks ({type(exc).__name__}: {exc})")
        news_fn = fetch_news

    from .validate import Issue, validate_run, write_quality_log
    issues = validate_run(universe, prices, funds, settings, today)
    issues += [Issue(t, "price_source", "warn", "Yahoo had no data; used unadjusted OpenBB bars (dividends not adjusted)")
               for t, s in source.items() if s == "fallback"]
    if not a.demo:
        issues += [Issue(i.name, "index_missing", "warn", f"no data for {i.symbol}; no market context from it for region {i.region}")
                   for i in settings.all_indices if i.symbol not in {x["symbol"] for x in indices}]
        if not a.no_crosscheck:
            issues += _crosscheck(tickers, prices, today)

    payload = build_payload(universe, prices, funds, settings, news_fn=news_fn, demo=a.demo, today=today, fx_to_usd=fx,
                            indices=indices, issues=issues, index_history=idx_hist, earnings=earnings)
    for d in payload["data_quality"]:
        print(f"  skipped {d['t']}: {d['detail']}")
    fallers = [r for r in payload["rows"] if needs_news(r, settings.news)]
    if fallers and not a.demo and not any(r["news"] for r in fallers):
        issues.append(Issue("*", "news_unavailable", "warn", f"no headlines returned for any of {len(fallers)} fallers"))
        payload["issues"] = [asdict(i) for i in issues]
    out_path = Path(a.out)
    need = max(1, math.ceil(settings.data.min_screened_fraction * len(universe)))
    if len(payload["rows"]) < need:
        # A half-empty pull must not replace yesterday's good files. Keep them, record why, and fail loudly.
        write_quality_log(issues, out_path.parent / "data_quality.failed.csv")
        print(f"FAILED: only {len(payload['rows'])} of {len(universe)} stocks could be screened (minimum {need}). "
              f"The dashboard, digest and history were left as they were; see data_quality.failed.csv.")
        return 2

    (out_path.parent / "data_quality.failed.csv").unlink(missing_ok=True)       # a stale failure note from an earlier night would mislead
    asof = max(r["asof"] for r in payload["rows"])
    history_dir = out_path.parent / "history"
    repeat = asof in history_dates(history_dir)
    alerts = _alerts(payload, prices, asof, out_path, data_dir, a.demo, repeat)
    payload["alerts"] = alerts
    out = write_dashboard(payload, out_path)
    print(f"Wrote {out} ({len(payload['rows'])} stocks)")
    digest_text = build_digest(payload, settings, backtest_line=latest_backtest_line(out_path.parent), repeat=repeat,
                               alerts=alerts, alerts_failed=alerts is None)
    digest_path = atomic_write_text(a.digest or out_path.parent / "digest.md", digest_text)
    print(f"Wrote {digest_path}")
    log = write_quality_log(issues, out_path.parent / ("data_quality.demo.csv" if a.demo else "data_quality.csv"))   # a demo run must not replace a real log
    n = {k: sum(i.severity == k for i in issues) for k in ("error", "warn", "info")}
    print(f"Data quality: {n['error']} error(s), {n['warn']} warning(s) -> {log}")
    if a.history:
        for src, name in ((out, f"dashboard_{asof}.html"), (digest_path, f"digest_{asof}.md"), (log, f"data_quality_{asof}.csv")):
            atomic_write_text(history_dir / name, src.read_text(encoding="utf-8"))
        print(f"History copies for data date {asof} -> {history_dir}")
        packed = _compress_old_history(history_dir, asof)
        if packed:
            print(f"  compressed {packed} older dashboard copies")
    if a.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def _crosscheck(tickers: list[str], prices: dict, today: date, n: int = 5) -> list:
    """Compare five random tickers with an independent source (US via Nasdaq, Nordic via Nasdaq Nordic)."""
    import importlib.util

    from . import openbb_source
    from .crosscheck import pick_sample, run_crosscheck, to_issues
    from .data import fetch_raw_closes

    if importlib.util.find_spec("openbb") is None:                  # OpenBB is optional (about 1 GB); say so instead of pretending to compare
        print("Cross-check skipped: OpenBB is not installed (pip install openbb==5.0.0 to enable it).")
        return []

    eligible = [t for t in tickers if t in prices and openbb_source.source_for(t)]
    sample = pick_sample(eligible, n, seed=int(today.strftime("%Y%m%d")))
    print(f"Cross-checking {len(sample)} tickers against a second source: {', '.join(sample)}")

    def other(t):
        src = openbb_source.source_for(t)
        return (src, lambda s, e: (lambda b: b[0] if b else None)(openbb_source.fetch_bars(t, s, e))) if src else None

    return to_issues(run_crosscheck(sample, fetch_ref=fetch_raw_closes, fetch_other=other, today=today))
