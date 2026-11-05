"""Forward ledger (RES-5): every night's screen is recorded as it was, and scored later.

This is the only test free of survivorship bias, because the stocks are written down before their outcome is known.
It needs years, not weeks, to have any power. The file is append-only: earlier bytes are never rewritten, the first
complete row for (asof, ticker) wins, and a stock whose last bar is still partial is not recorded that night.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import cluster_bootstrap
from .config import Settings
from .provenance import settings_section_hashes

LEDGER_COLS = ["asof", "ticker", "region", "flagged", "setup", "q", "knife", "settings_hash", "universe_hash", "recorded_at"]
SETTINGS_SECTIONS = ("dip", "quality", "falling_knife")     # the sections that decide what is flagged
MIN_FLAGGED = 30                                            # below this many matured flagged rows no interval is shown
_BOOLS = {"True", "False"}


def settings_hash(s: Settings) -> str:
    """One 16-hex hash over the dip, quality and falling_knife sections (built from provenance's per-section hashes)."""
    sec = settings_section_hashes(s)
    body = json.dumps({k: sec[k] for k in SETTINGS_SECTIONS}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def file_hash(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ledger_rows(payload: dict, settings_hash: str, universe_hash: str, now: datetime) -> pd.DataFrame:
    """One row per screened stock whose last bar is complete. Unflagged stocks are kept: they are the same-date baseline."""
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    recs = []
    for r in payload["rows"]:
        if r.get("partial"):
            continue
        q = r.get("q")
        recs.append({"asof": r["asof"], "ticker": r["t"], "region": r["region"], "flagged": bool(r["dip"]), "setup": r["setup"],
                     "q": "" if q is None else int(q), "knife": bool(r["knife"]), "settings_hash": settings_hash,
                     "universe_hash": universe_hash, "recorded_at": stamp})
    return pd.DataFrame(recs, columns=LEDGER_COLS)


def _complete(fields: list[str]) -> bool:
    if len(fields) != len(LEDGER_COLS):
        return False
    d = dict(zip(LEDGER_COLS, fields))
    try:
        datetime.strptime(d["asof"], "%Y-%m-%d")
    except ValueError:
        return False
    return bool(d["ticker"]) and d["flagged"] in _BOOLS and d["knife"] in _BOOLS and bool(d["recorded_at"])


def _fragment(fields: list[str]) -> bool:
    """The leftover of a crash in the middle of a row: it starts like a row (a date) but stops short. Skipped, not counted."""
    try:
        datetime.strptime(fields[0], "%Y-%m-%d")
    except (ValueError, IndexError):
        return False
    return len(fields) < len(LEDGER_COLS)


def _parse(path: Path) -> tuple[list[list[str]], bool]:
    """Complete rows of an existing ledger, and whether it ends without a newline.
    A bad header, or a bad row that is not a crash fragment, means the file is corrupt: ValueError."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")                                # UnicodeDecodeError is a ValueError
    lines = text.split("\n")
    unterminated = bool(text) and not text.endswith("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return [], unterminated
    try:
        parsed = [next(csv.reader([ln.rstrip("\r")]), []) for ln in lines]
    except csv.Error as exc:
        raise ValueError(f"{path}: not a readable ledger ({exc})") from exc
    if parsed[0] != LEDGER_COLS:
        raise ValueError(f"{path}: header is not the ledger header")
    good = []
    for i, f in enumerate(parsed[1:], start=1):
        if _complete(f):
            good.append(f)
        elif not (_fragment(f) or (unterminated and i == len(parsed) - 1)):
            raise ValueError(f"{path}: line {i + 1} is not a complete ledger row")
    return good, unterminated


def read_ledger(path: Path | str) -> pd.DataFrame:
    """Complete rows only, typed; an unfinished last line is skipped. Raises ValueError for a corrupt file."""
    good, _ = _parse(Path(path))
    df = pd.DataFrame(good, columns=LEDGER_COLS)
    df["flagged"] = df["flagged"] == "True"
    df["knife"] = df["knife"] == "True"
    return df


def append_rows(path: Path, rows: pd.DataFrame) -> int:
    """Append rows whose (asof, ticker) is not in the file yet; return how many were written. Never rewrites earlier bytes.
    The header is written only for a new (or empty) file. A corrupt file raises ValueError and is left as it was."""
    path = Path(path)
    existing: set[tuple[str, str]] = set()
    prefix = ""
    new_file = True
    if path.exists():
        if path.is_dir():
            raise IsADirectoryError(str(path))
        good, unterminated = _parse(path)
        existing = {(f[0], f[1]) for f in good}
        new_file = path.stat().st_size == 0
        prefix = "\n" if unterminated else ""                 # a crash mid-row: close that line so rows never glue together
    fresh, seen = [], set(existing)
    for rec in rows[LEDGER_COLS].astype(str).itertuples(index=False):
        key = (rec[0], rec[1])
        if key not in seen:
            seen.add(key)
            fresh.append(list(rec))
    if not fresh:
        return 0
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if new_file:
        w.writerow(LEDGER_COLS)
    w.writerows(fresh)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:                               # one write call; bytes are UTF-8 with "\n" on every platform
        fh.write((prefix + buf.getvalue()).encode("utf-8"))
    return len(fresh)


def record_run(payload: dict, s: Settings, universe_path: Path | str, ledger_path: Path, now: datetime | None = None) -> int:
    """What the daily run calls: build tonight's rows and append them. Returns the number of new rows."""
    now = now or datetime.now(timezone.utc)
    return append_rows(ledger_path, ledger_rows(payload, settings_hash(s), file_hash(universe_path), now))


def score(ledger: pd.DataFrame, prices: dict[str, pd.Series], horizons=(5, 21, 63)) -> pd.DataFrame:
    """Forward returns per ledger row. Entry is the first close strictly after asof; exit is h bars after entry
    (the same convention as the backtest). A row with no entry or no exit keeps an empty cell; a stock that is
    missing from `prices` stays in the output with empty cells."""
    out = ledger.copy()
    entry_dates = []
    fwd = {h: [] for h in horizons}
    for asof, ticker in zip(out["asof"], out["ticker"]):
        s = prices.get(ticker)
        pos, closes, idx = None, None, None
        if s is not None and len(s):
            s = s.dropna().sort_index()
            idx = pd.DatetimeIndex(s.index)
            closes = s.to_numpy(dtype=float)
            p = int(idx.searchsorted(pd.Timestamp(asof), side="right"))
            pos = p if p < len(idx) else None
        entry_dates.append("" if pos is None else idx[pos].strftime("%Y-%m-%d"))
        for h in horizons:
            ok = pos is not None and pos + h < len(closes)
            fwd[h].append(closes[pos + h] / closes[pos] - 1 if ok else np.nan)
    out["entry_date"] = entry_dates
    for h in horizons:
        out[f"fwd_{h}"] = fwd[h]
    return out


def _horizons(scored: pd.DataFrame) -> list[int]:
    return sorted(int(c[4:]) for c in scored.columns if c.startswith("fwd_"))


def summarize_scores(scored: pd.DataFrame, s: Settings) -> pd.DataFrame:
    """Per horizon: matured flagged and baseline counts, and flagged minus same-date unflagged, gross and net of cost,
    with a month-clustered interval. The difference is taken date by date, so the baseline is always the same date.
    The cost is charged to the flagged side only (the baseline is a yardstick, nobody trades it). Dates count equally.
    Fewer than MIN_FLAGGED matured flagged rows: the row says so and shows no interval."""
    b = s.backtest
    rows = []
    for h in _horizons(scored):
        col = f"fwd_{h}"
        d = scored.dropna(subset=[col])
        fl, base = d[d["flagged"].astype(bool)], d[~d["flagged"].astype(bool)]
        per = pd.DataFrame({"f": fl.groupby("asof")[col].mean(), "u": base.groupby("asof")[col].mean()}).dropna()
        gross = (per["f"] - per["u"]).to_numpy()
        net = gross - b.cost_roundtrip
        months = per.index.astype(str).str[:7].to_numpy()
        enough = len(fl) >= MIN_FLAGGED
        rec = {"horizon": h, "n_flagged": len(fl), "n_baseline": len(base), "n_dates": len(per),
               "n_months": len(set(months)), "gross_diff": np.nan, "gross_lo": np.nan, "gross_hi": np.nan,
               "net_diff": np.nan, "net_lo": np.nan, "net_hi": np.nan, "cost": b.cost_roundtrip, "note": ""}
        if len(per):
            rec["gross_diff"], rec["net_diff"] = float(gross.mean()), float(net.mean())
        if enough and len(per):
            _, rec["gross_lo"], rec["gross_hi"], _ = cluster_bootstrap(gross, months, b.bootstrap_draws, b.ci_level, b.seed)
            _, rec["net_lo"], rec["net_hi"], _ = cluster_bootstrap(net, months, b.bootstrap_draws, b.ci_level, b.seed)
        if not enough:
            rec["note"] = f"too few matured flagged rows ({len(fl)} of {MIN_FLAGGED} needed): no interval"
        elif np.isnan(rec["net_lo"]):
            rec["note"] = "only one calendar month so far: no interval"
        rows.append(rec)
    return pd.DataFrame(rows)
