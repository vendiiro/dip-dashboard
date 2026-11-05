"""Raw-pull cache: data/raw/<source>/<date>.csv.gz. A raw file is never overwritten."""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd


def save_raw_prices(prices: dict, source: str, root: Path | str, now: datetime | None = None) -> Path:
    """Write {ticker: (close, volume|None)} as one long CSV. A second pull on the same day gets a time suffix."""
    now = now or datetime.now()
    frames = []
    for t, (close, vol) in prices.items():
        df = pd.DataFrame({"ticker": t, "date": pd.to_datetime(close.index).strftime("%Y-%m-%d"), "close": close.to_numpy()})
        df["volume"] = vol.reindex(close.index).to_numpy() if vol is not None else float("nan")
        frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ticker", "date", "close", "volume"])
    folder = Path(root) / source
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y-%m-%d}.csv.gz"
    if path.exists():
        path = folder / f"{now:%Y-%m-%d}_{now:%H%M%S}.csv.gz"
    with gzip.open(path, "xt", encoding="utf-8", newline="") as fh:   # "x": fail rather than overwrite
        out.to_csv(fh, index=False)
    return path


def load_raw_prices(path: Path | str) -> dict:
    df = pd.read_csv(path, parse_dates=["date"])
    out = {}
    for t, g in df.groupby("ticker", sort=False):
        g = g.set_index("date")
        out[t] = (g["close"].astype(float), g["volume"].astype(float) if g["volume"].notna().any() else None)
    return out


def list_raw(source: str, root: Path | str) -> list[Path]:
    return sorted((Path(root) / source).glob("*.csv.gz"))


def atomic_write_json(path: Path | str, obj) -> Path:
    """Write JSON so a reader (or the next run) sees either the old file or the complete new one, never half of it.

    Temp file in the same folder, flush and fsync, then os.replace (atomic on one volume, also on Windows). If anything
    fails the temp file is removed and the original is untouched. A crash that kills the process leaves at most a stray
    *.tmp next to the target, which nothing reads."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return p
