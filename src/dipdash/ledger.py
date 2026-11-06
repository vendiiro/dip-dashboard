"""Forward ledger (RES-5): every night's screen is recorded as it was, and scored later.

The record is fixed in advance: each night's rows are written before the outcome is known, so nothing can be added or
dropped in hindsight. That is not the same as being free of every bias. A stock that is delisted or acquired later has
no later price and cannot be scored; such rows are counted as unscored, and they may be the worst outcomes.
It needs years, not weeks, to have any power. The file is append-only: earlier bytes are never rewritten, the first
complete row for (asof, ticker) wins, and a stock whose last bar may still be partial is not recorded that night.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .backtest import cluster_bootstrap
from .config import Settings
from .exchanges import exchange_for
from .provenance import code_hash, settings_section_hashes

SCHEMA_VERSION = "1"
LEDGER_COLS = ["asof", "ticker", "region", "flagged", "setup", "q", "knife", "settings_hash", "universe_hash",
               "code_hash", "schema_version", "detail", "recorded_at"]      # recorded_at stays last: a cut row reads as a fragment
RUNS_COLS = ["recorded_at", "asof", "universe_size", "screened", "rows_written", "partial_count", "too_soon_count", "skipped"]
SETTINGS_SECTIONS = ("dip", "quality", "falling_knife")     # the sections that decide what is flagged
DETAIL_FIELDS = ("price", "r1", "r5", "dd20", "vs200", "dd52", "why", "q_status", "q_scored", "q_applicable", "q_passed",
                 "q_must_failed", "q_must_missing", "earn")           # the payload has no per-row price source; the run adds it
MIN_FLAGGED = 30                                            # an interval needs at least this many events after the cooldown ...
MIN_MONTHS = 12                                             # ... spread over at least this many calendar months
MAX_ENTRY_GAP_DAYS = 7                                      # the entry bar must be this close to the signal date
SAFETY_HOURS = 2                                            # a row is recorded only if the run started this long after the close
_REQUIRED = {"asof", "ticker", "flagged", "recorded_at"}
_BOOLS = {"True", "False"}


def settings_hash(s: Settings) -> str:
    """One 16-hex hash over the dip, quality and falling_knife sections (built from provenance's per-section hashes)."""
    sec = settings_section_hashes(s)
    body = json.dumps({k: sec[k] for k in SETTINGS_SECTIONS}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def file_hash(path: Path | str) -> str:
    """sha256 of a text file with CRLF and LF hashing the same (as provenance.code_hash does)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _detail(r: dict, price_source: str | None) -> str:
    d = {k: r[k] for k in DETAIL_FIELDS if k in r}
    if price_source:
        d["price_source"] = price_source
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _close_utc(ticker: str, asof: str) -> datetime | None:
    ex = exchange_for(ticker)
    if ex is None:
        return None
    local = datetime.combine(datetime.strptime(asof, "%Y-%m-%d").date(), ex.close, tzinfo=ZoneInfo(ex.tz))
    return local.astimezone(timezone.utc)


def prepare_rows(payload: dict, settings_hash: str, universe_hash: str, now: datetime, *, code: str = "",
                 run_started: datetime | None = None, price_source: dict | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Rows to record, and {ticker: reason} for every stock left out. Unflagged stocks are kept: they are the same-date baseline.
    A stock is left out when its last bar may be partial, or when the run started less than SAFETY_HOURS after that
    exchange's close on the bar's date (a price taken around the close can still be mid-session)."""
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    skipped = {d["t"]: d.get("reason", "left_out") for d in payload.get("data_quality", []) if "t" in d}
    recs = []
    for r in payload["rows"]:
        if r.get("partial"):
            skipped[r["t"]] = "partial"
            continue
        close = _close_utc(r["t"], r["asof"]) if run_started is not None else None
        if close is not None and (run_started - close).total_seconds() < SAFETY_HOURS * 3600:
            skipped[r["t"]] = "too_soon"
            continue
        q = r.get("q")
        recs.append({"asof": r["asof"], "ticker": r["t"], "region": r["region"], "flagged": bool(r["dip"]), "setup": r["setup"],
                     "q": "" if q is None else int(q), "knife": bool(r["knife"]), "settings_hash": settings_hash,
                     "universe_hash": universe_hash, "code_hash": code, "schema_version": SCHEMA_VERSION,
                     "detail": _detail(r, (price_source or {}).get(r["t"])), "recorded_at": stamp})
    return pd.DataFrame(recs, columns=LEDGER_COLS), skipped


def ledger_rows(payload: dict, settings_hash: str, universe_hash: str, now: datetime, **kw) -> pd.DataFrame:
    return prepare_rows(payload, settings_hash, universe_hash, now, **kw)[0]


def _known_header(h: list[str]) -> bool:
    return len(set(h)) == len(h) and set(h) <= set(LEDGER_COLS) and _REQUIRED <= set(h) and h[-1] == "recorded_at"


def _complete(fields: list[str], header: list[str]) -> bool:
    if len(fields) != len(header):
        return False
    d = dict(zip(header, fields))
    try:
        datetime.strptime(d["asof"], "%Y-%m-%d")
    except ValueError:
        return False
    return (bool(d["ticker"]) and d["flagged"] in _BOOLS and d.get("knife", "False") in _BOOLS and bool(d["recorded_at"]))


def _fragment(fields: list[str], header: list[str]) -> bool:
    """The leftover of a crash in the middle of a row: it starts like a row (a date) but stops short. Skipped, not counted."""
    try:
        datetime.strptime(fields[0], "%Y-%m-%d")
    except (ValueError, IndexError):
        return False
    return len(fields) < len(header)


def _parse(path: Path) -> tuple[list[str], list[list[str]], bool]:
    """(header, complete rows, ends-without-newline) of an existing ledger. Columns are read by header name, so an older
    header (fewer columns) still works; only an unknown header, or a bad row that is not a crash fragment, is corrupt: ValueError.
    A byte-order mark in front of the header is ignored."""
    text = path.read_bytes().decode("utf-8")                 # UnicodeDecodeError is a ValueError
    if text.startswith("﻿"):
        text = text[1:]
    unterminated = bool(text) and not text.endswith("\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return list(LEDGER_COLS), [], unterminated
    try:
        parsed = [next(csv.reader([ln.rstrip("\r")]), []) for ln in lines]
    except csv.Error as exc:
        raise ValueError(f"{path}: not a readable ledger ({exc})") from exc
    header = parsed[0]
    if not _known_header(header):
        raise ValueError(f"{path}: header is not a known ledger header")
    good = []
    for i, f in enumerate(parsed[1:], start=1):
        if _complete(f, header):
            good.append(f)
        elif not (_fragment(f, header) or (unterminated and i == len(parsed) - 1)):
            raise ValueError(f"{path}: line {i + 1} is not a complete ledger row")
    return header, good, unterminated


def read_ledger(path: Path | str) -> pd.DataFrame:
    """Complete rows only, typed, one per (asof, ticker) with the first winning; a cut last line is skipped.
    Columns an older header lacked are empty. Raises ValueError for a corrupt file."""
    header, good, _ = _parse(Path(path))
    df = pd.DataFrame(good, columns=header)
    for c in LEDGER_COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[LEDGER_COLS].drop_duplicates(["asof", "ticker"], keep="first").reset_index(drop=True)
    df["flagged"] = df["flagged"] == "True"
    df["knife"] = df["knife"] == "True"
    return df


def append_rows(path: Path, rows: pd.DataFrame) -> int:
    """Append rows whose (asof, ticker) is not in the file yet; return how many were written. Never rewrites earlier bytes.
    The header is written only for a new (or empty) file; rows follow the file's own header. A corrupt file raises
    ValueError and is left as it was."""
    path = Path(path)
    existing: set[tuple[str, str]] = set()
    prefix, new_file, cols = "", True, list(LEDGER_COLS)
    if path.exists():
        if path.is_dir():
            raise IsADirectoryError(str(path))
        header, good, unterminated = _parse(path)
        new_file = path.stat().st_size == 0
        if not new_file:
            cols = header
        d = {c: i for i, c in enumerate(header)}
        existing = {(f[d["asof"]], f[d["ticker"]]) for f in good}
        prefix = "\n" if unterminated else ""                 # a crash mid-row: close that line so rows never glue together
    fresh, seen = [], set(existing)
    for rec in rows.to_dict("records"):
        key = (str(rec["asof"]), str(rec["ticker"]))
        if key not in seen:
            seen.add(key)
            fresh.append(["" if rec.get(c) is None else str(rec.get(c, "")) for c in cols])
    if not fresh:
        return 0
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if new_file:
        w.writerow(cols)
    w.writerows(fresh)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:                               # one write call; UTF-8 with "\n" on every platform
        fh.write((prefix + buf.getvalue()).encode("utf-8"))
    return len(fresh)


def _keep_copy(src: Path, dest: Path) -> None:
    """Copy a rule file next to the ledger under its hash. Never overwrites."""
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)


def _backup(path: Path) -> None:
    """Atomic copy of the (already checked) ledger to flags.backup.csv in the same folder."""
    tmp = path.with_name(path.stem + ".backup.csv.tmp")
    shutil.copyfile(path, tmp)
    os.replace(tmp, path.with_name(path.stem + ".backup.csv"))


def _append_run(path: Path, rec: dict) -> None:
    new = not path.exists() or path.stat().st_size == 0
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if new:
        w.writerow(RUNS_COLS)
    w.writerow([rec[c] for c in RUNS_COLS])
    with path.open("ab") as fh:
        fh.write(buf.getvalue().encode("utf-8"))


def record_run(payload: dict, s: Settings, universe_path: Path | str, ledger_path: Path, *, settings_path: Path | str | None = None,
               run_started: datetime | None = None, now: datetime | None = None, universe_size: int | None = None,
               price_source: dict | None = None, src_dir: Path | None = None) -> int:
    """What the daily run calls: build tonight's rows, keep the rule files under their hashes, back the ledger up, append,
    and add one line to runs.csv. Returns the number of new rows."""
    now = now or datetime.now(timezone.utc)
    ledger_path = Path(ledger_path)
    sh, uh = settings_hash(s), file_hash(universe_path)
    code = code_hash(src_dir or Path(__file__).resolve().parent)
    rows, skipped = prepare_rows(payload, sh, uh, now, code=code, run_started=run_started, price_source=price_source)
    versions = ledger_path.parent / "versions"
    if settings_path is not None:
        _keep_copy(Path(settings_path), versions / f"{sh}.toml")
    _keep_copy(Path(universe_path), versions / f"{uh}.csv")
    if ledger_path.exists() and not ledger_path.is_dir():
        read_ledger(ledger_path)                              # raises on a corrupt file, so a bad file never overwrites a good backup
        _backup(ledger_path)
    n = append_rows(ledger_path, rows)
    _append_run(ledger_path.parent / "runs.csv", {
        "recorded_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asof": max((r["asof"] for r in payload["rows"]), default=""), "universe_size": universe_size or "",
        "screened": len(payload["rows"]), "rows_written": n,
        "partial_count": sum(v == "partial" for v in skipped.values()), "too_soon_count": sum(v == "too_soon" for v in skipped.values()),
        "skipped": json.dumps(skipped, sort_keys=True, separators=(",", ":"))})
    return n


_RAW_TIME = re.compile(r"_(\d{2})(\d{2})(\d{2})\.csv\.gz$")


def pick_raw(files: list[Path]) -> tuple[Path | None, str]:
    """The newest raw price pull that was not taken during trading hours, and a warning when a newer one was passed over.
    A second pull on a day gets a time suffix; a local time between 08:00 and 22:00 is treated as mid-session."""
    def mid(p: Path) -> bool:
        m = _RAW_TIME.search(p.name)
        return bool(m) and 8 <= int(m.group(1)) < 22
    files = sorted(files)
    if not files:
        return None, ""
    complete = [p for p in files if not mid(p)]
    if complete:
        pick = complete[-1]
        return pick, (f"newer pull {files[-1].name} was taken mid-session; used {pick.name}" if files[-1] != pick else "")
    return files[-1], f"every pull was taken mid-session; used {files[-1].name}, its last bars may be partial"


def score(ledger: pd.DataFrame, prices: dict[str, pd.Series], horizons=(5, 21, 63)) -> pd.DataFrame:
    """Forward returns per ledger row. A row needs a bar on its own date and an entry bar (the first close strictly after
    asof) within MAX_ENTRY_GAP_DAYS calendar days; exit is h bars after entry (the backtest's convention). Otherwise the
    cells stay empty and `reason` says why. A stock missing from `prices` stays in the output, empty.
    Extra columns: entry_date, bar (position of the asof bar), reason, late (recorded after the entry bar's date),
    due_<h> (the price calendar says this row should have matured by now)."""
    out = ledger.copy().reset_index(drop=True)
    series = {t: s.dropna().sort_index() for t, s in prices.items() if s is not None and len(s.dropna())}
    ref = pd.DatetimeIndex(sorted(set().union(*[set(s.index) for s in series.values()]))) if series else pd.DatetimeIndex([])
    entry_dates, bars, reasons, late = [], [], [], []
    fwd = {h: [] for h in horizons}
    due = {h: [] for h in horizons}
    recs = out["recorded_at"].astype(str).tolist() if "recorded_at" in out.columns else [""] * len(out)
    for asof, ticker, rec in zip(out["asof"], out["ticker"], recs):
        a = pd.Timestamp(asof)
        s = series.get(ticker)
        reason, pos, entry = "", None, None
        if s is None:
            reason = "no_price_series"
        else:
            idx = pd.DatetimeIndex(s.index)
            p = int(idx.searchsorted(a, side="left"))
            if p >= len(idx) or idx[p] != a:
                reason = "no_bar_at_asof"
            elif p + 1 >= len(idx):
                reason = "no_later_bar"
            elif (idx[p + 1] - a).days > MAX_ENTRY_GAP_DAYS:
                reason = "entry_gap_over_7_days"
            else:
                pos, entry = p, p + 1
        closes = s.to_numpy(dtype=float) if s is not None else None
        entry_dates.append(pd.DatetimeIndex(s.index)[entry].strftime("%Y-%m-%d") if entry is not None else "")
        bars.append(np.nan if pos is None else pos)
        reasons.append(reason)
        late.append(bool(entry is not None and rec[:10] > entry_dates[-1] and rec != ""))
        n_after = len(ref) - int(ref.searchsorted(a, side="right"))
        for h in horizons:
            ok = entry is not None and entry + h < len(closes)
            fwd[h].append(closes[entry + h] / closes[entry] - 1 if ok else np.nan)
            due[h].append(n_after >= h + 1)
    out["entry_date"], out["bar"], out["reason"], out["late"] = entry_dates, bars, reasons, late
    for h in horizons:
        out[f"fwd_{h}"], out[f"due_{h}"] = fwd[h], due[h]
    return out


def _horizons(scored: pd.DataFrame) -> list[int]:
    return sorted(int(c[4:]) for c in scored.columns if c.startswith("fwd_"))


def _positions(d: pd.DataFrame) -> np.ndarray:
    """Trading-day position of each row: the bar number in the price series when scoring recorded it, else a weekday count."""
    if "bar" in d.columns and d["bar"].notna().all():
        return d["bar"].to_numpy(dtype=float)
    return np.busday_count("1970-01-01", d["asof"].astype(str).to_numpy(dtype="datetime64[D]")).astype(float)


def after_cooldown(flagged: pd.DataFrame, cooldown_days: int) -> pd.Series:
    """True for the rows kept: per stock, a flagged row counts only if at least `cooldown_days` trading days (price-series
    bars, not ledger rows) have passed since the stock's previous kept row. Consecutive nights are one event."""
    keep = pd.Series(False, index=flagged.index)
    pos = pd.Series(_positions(flagged), index=flagged.index)
    for _, g in flagged.assign(_pos=pos).sort_values(["ticker", "_pos"]).groupby("ticker"):
        last = -np.inf
        for ix, p in zip(g.index, g["_pos"]):
            if p - last >= cooldown_days:
                keep[ix] = True
                last = p
    return keep


def _one(d: pd.DataFrame, fl_mask: pd.Series, h: int, b, allow_interval: bool | None) -> dict:
    col = f"fwd_{h}"
    due = d[f"due_{h}"].astype(bool) if f"due_{h}" in d.columns else d[col].notna()
    ok = d[col].notna()
    fl_all, base_all = d[fl_mask], d[~d["flagged"].astype(bool)]
    fl, base = fl_all[ok[fl_all.index]], base_all[ok[base_all.index]]
    per = pd.DataFrame({"f": fl.groupby("asof")[col].mean(), "u": base.groupby("asof")[col].mean()}).dropna()
    fl = fl[fl["asof"].isin(per.index)]
    gross = (per["f"] - per["u"]).to_numpy()
    net = gross - b.cost_roundtrip
    months = per.index.astype(str).str[:7].to_numpy()
    excess = (fl[col].to_numpy() - per["u"].reindex(fl["asof"]).to_numpy())
    rec = {"n_flagged": len(fl), "n_baseline": int(base["asof"].isin(per.index).sum()),
           "n_unscored": int((due[fl_all.index] & ~ok[fl_all.index]).sum()), "n_unscored_base": int((due[base_all.index] & ~ok[base_all.index]).sum()),
           "n_dates": len(per), "n_months": len(set(months)), "gross_diff": np.nan, "gross_lo": np.nan, "gross_hi": np.nan,
           "net_diff": np.nan, "net_lo": np.nan, "net_hi": np.nan, "net_diff_2x": np.nan,
           "med_excess": np.nan, "p10_excess": np.nan, "p90_excess": np.nan, "cost": b.cost_roundtrip, "note": ""}
    enough = rec["n_flagged"] >= MIN_FLAGGED and rec["n_months"] >= MIN_MONTHS
    rec["enough"] = enough
    if len(per):
        rec["gross_diff"], rec["net_diff"] = float(gross.mean()), float(net.mean())
        rec["net_diff_2x"] = float(gross.mean() - 2 * b.cost_roundtrip)
        rec["med_excess"], rec["p10_excess"], rec["p90_excess"] = (float(x) for x in np.nanpercentile(excess, [50, 10, 90]))
    if enough and allow_interval is not False and len(per):
        _, rec["gross_lo"], rec["gross_hi"], _ = cluster_bootstrap(gross, months, b.bootstrap_draws, b.ci_level, b.seed)
        _, rec["net_lo"], rec["net_hi"], _ = cluster_bootstrap(net, months, b.bootstrap_draws, b.ci_level, b.seed)
    if not enough:
        rec["note"] = (f"too few for an interval: {rec['n_flagged']} events over {rec['n_months']} calendar months "
                       f"(needs {MIN_FLAGGED} events and {MIN_MONTHS} months). Means only")
    elif allow_interval is False:
        rec["note"] = "no interval: the after-cooldown view does not have enough events yet"
    return rec


def summarize_scores(scored: pd.DataFrame, s: Settings) -> pd.DataFrame:
    """Flagged minus same-date unflagged, per rule version (settings_hash), section (any dip, Quality dip only), view
    (after cooldown first, all nights second) and horizon. Never pools rule versions. Gross is before costs; net subtracts
    one round-trip cost from the flagged side only; net_diff_2x doubles that cost. The difference is taken date by date,
    dates counting equally, and the interval resamples whole calendar months. An interval needs MIN_FLAGGED events and
    MIN_MONTHS months in the after-cooldown view; the all-nights interval additionally needs that view to qualify.
    Rows recorded after their entry bar are excluded (n_late). Rows old enough to have matured but with no price are n_unscored."""
    b = s.backtest
    rows = []
    versions = sorted(scored["settings_hash"].astype(str).unique()) if "settings_hash" in scored.columns else [""]
    for v in versions:
        sub = scored[scored["settings_hash"].astype(str) == v] if "settings_hash" in scored.columns else scored
        n_late = int(sub["late"].astype(bool).sum()) if "late" in sub.columns else 0
        if n_late:
            sub = sub[~sub["late"].astype(bool)]
        sub = sub.copy()
        sub["flagged"] = sub["flagged"].astype(bool)
        sections = [("any dip", sub["flagged"])]
        if "setup" in sub.columns:
            sections.append(("Quality dip only", sub["flagged"] & (sub["setup"] == "Quality dip")))
        for name, mask in sections:
            keep = after_cooldown(sub[mask], b.cooldown_days)
            views = (("after cooldown", mask & keep.reindex(sub.index, fill_value=False)), ("all nights", mask))
            qualifies = {}
            for view, fmask in views:
                for h in _horizons(sub):
                    rec = _one(sub, fmask, h, b, None if view == "after cooldown" else qualifies.get(h, False) or False)
                    if view == "after cooldown":
                        qualifies[h] = rec["enough"]
                    rows.append({"settings_hash": v, "section": name, "view": view, "horizon": h, **{k: x for k, x in rec.items() if k != "enough"},
                                 "n_late": n_late})
    return pd.DataFrame(rows)
