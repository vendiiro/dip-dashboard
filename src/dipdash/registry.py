"""One pre-registration and trial registry for every research runner (backtest, feature experiment, forecast calibration).

Rules (backtest-hygiene rule 1, made testable):
- `spec_hash` is the one canonical hash: sha256 of the sorted-key JSON of the spec, first 16 hex characters. Descriptive keys
  (per kind, see EXCLUDED) and the `registration` block are left out, so editing a note never changes the identity of an analysis.
- `register` runs BEFORE any return is computed. It checks the required fields, writes `spec_<hash>.json` once (never
  overwritten), appends a row to `registry.csv` and returns a `Registration` token.
- `record_trials` is the only writer of the trial log `trials_all.csv`. It refuses without a token from `register` (or `backfill`),
  refuses rows that carry another spec hash, and refuses more cells than the registration planned.
- The period ledger is derived from `registry.csv`: when a new registration's out-of-sample window overlaps one that was already
  registered (any kind), that is recorded in the spec's `registration.oos_reuse` (not hashed) and printed in the report.
  Reuse is a note, never a block (Iiro's choice, 2026-11-04).

stdlib + pandas only. Run `python -m dipdash.registry backfill --root output/backtests` once to import the hashes and trial rows
of the older per-runner trial logs (`trials.csv`, `trials_features.csv`); the old files are only read, never changed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

KINDS = ("backtest", "features", "forecast")
EXCLUDED: dict[str, frozenset[str]] = {                     # descriptive keys per kind; never part of the hash
    "backtest": frozenset({"revisions_after_first_look", "sample_notes"}),
    "features": frozenset({"notes"}),
    "forecast": frozenset({"notes"}),
}
ALWAYS_EXCLUDED = frozenset({"spec_hash", "registration"})  # the hash itself and the registry's own block
REGISTRY_FILE, TRIALS_FILE = "registry.csv", "trials_all.csv"
REGISTRY_COLS = ["registered_at", "kind", "family_id", "spec_hash", "source", "split_cutoff", "oos_start", "oos_end", "horizons",
                 "raw_sha256", "planned_cells", "note"]
TRIAL_COLS = ["run_at", "kind", "family_id", "spec_hash", "cell", "stat", "group", "period", "horizon", "n", "estimate", "lo", "hi",
              "p_raw", "p_holm", "primary"]
REQUIRED = ("family_id", "hypothesis", "pass_fail", "split_cutoff", "oos_start", "oos_end", "horizons", "planned_cells", "raw_sha256")

# Where each kind's spec already holds a required field (dotted path). Anything not here comes from `fields` at registration.
SPEC_PATHS: dict[str, dict[str, str]] = {
    "backtest": {"hypothesis": "primary_hypothesis", "pass_fail": "primary_cell", "split_cutoff": "split.cutoff",
                 "horizons": "horizons", "planned_cells": "cells_computed", "raw_sha256": "data.raw_sha256"},
    "features": {"family_id": "family_id", "hypothesis": "family.test", "pass_fail": "supported_means",
                 "split_cutoff": "split.cutoff_last_in_sample_date", "raw_sha256": "parent_backtest_spec.raw_sha256"},
    "forecast": {"family_id": "family_id", "hypothesis": "criterion_text", "pass_fail": "verdict_rule.text",
                 "split_cutoff": "split.cutoff", "horizons": "design.horizons", "planned_cells": "planned_cells",
                 "raw_sha256": "data.raw_sha256"},
}

_ISSUED: dict[str, int] = {}                                # token -> trial rows written so far under it (this process only)


class RegistrationError(RuntimeError):
    """A runner tried to log trials without registering first, or the registration is inconsistent."""


# ---------------------------------------------------------------- hash
def spec_hash(spec: dict, excluded_keys=frozenset()) -> str:
    """The one canonical spec hash. Pinned by a golden test: changing this function changes every recorded hash."""
    drop = set(excluded_keys) | ALWAYS_EXCLUDED
    body = {k: v for k, v in spec.items() if k not in drop}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


def hash_for(kind: str, spec: dict) -> str:
    _check_kind(kind)
    return spec_hash(spec, EXCLUDED[kind])


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise RegistrationError(f"unknown kind {kind!r}; expected one of {KINDS}")


# ---------------------------------------------------------------- registration
@dataclass(frozen=True)
class Registration:
    kind: str
    family_id: str
    spec_hash: str
    registered_at: str
    root: Path
    spec_file: Path | None
    planned_cells: int | None
    oos_start: str
    oos_end: str
    source: str = "registered"
    oos_reuse: tuple[str, ...] = ()
    _token: str = field(default="", repr=False, compare=False)

    @property
    def trials_path(self) -> Path:
        return Path(self.root) / TRIALS_FILE

    def reuse_note(self) -> str:
        """One paragraph for the report. Always non-empty, so a reader sees that the check ran."""
        return " ".join(self.oos_reuse) if self.oos_reuse else (
            f"No earlier registration in `{REGISTRY_FILE}` used an out-of-sample window overlapping {self.oos_start} to {self.oos_end}.")


def _get(spec: dict, path: str):
    cur = spec
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _norm(name: str, value):
    """Field values as they are stored in registry.csv (text), so spec and runner values can be compared."""
    if value is None:
        return None
    if name == "horizons":
        vals = list(value) if isinstance(value, (list, tuple)) else [value]
        return ";".join(str(int(v)) for v in vals)
    if name == "planned_cells":
        return str(int(value))
    if name in ("split_cutoff", "oos_start", "oos_end"):
        return str(pd.Timestamp(value).date())
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value).strip()


def resolve_fields(kind: str, spec: dict, fields: dict | None = None) -> dict[str, str]:
    """Required fields from the spec (where it holds them) and from `fields` (the rest, e.g. the out-of-sample window computed from
    dates). Both given and different -> error. Anything missing or empty -> error, naming every missing field."""
    _check_kind(kind)
    fields = dict(fields or {})
    unknown = set(fields) - set(REQUIRED)
    if unknown:
        raise RegistrationError(f"unknown registration fields: {sorted(unknown)}")
    out, missing = {}, []
    for name in REQUIRED:
        from_spec = _norm(name, _get(spec, SPEC_PATHS[kind][name])) if name in SPEC_PATHS[kind] else None
        given = _norm(name, fields.get(name))
        if from_spec is not None and given is not None and from_spec != given:
            raise RegistrationError(f"{name}: the spec says {from_spec!r}, the runner says {given!r}")
        val = from_spec if from_spec is not None else given
        if val is None or val == "" or val == "{}":
            missing.append(name)
        else:
            out[name] = val
    if missing:
        raise RegistrationError(f"{kind} spec cannot be registered; missing required fields: {', '.join(missing)}")
    if int(out["planned_cells"]) <= 0:
        raise RegistrationError("planned_cells must be positive")
    if not (out["split_cutoff"] < out["oos_start"] <= out["oos_end"]):
        raise RegistrationError(f"out-of-sample window {out['oos_start']}..{out['oos_end']} must start after the split cutoff {out['split_cutoff']}")
    return out


def register(kind: str, spec: dict, out_dir: Path | str, root: Path | str, fields: dict | None = None,
             now: datetime | None = None) -> Registration:
    """Pre-register a spec BEFORE computing anything. Writes `out_dir/spec_<hash>.json` once (an existing file is kept as it was),
    appends a row to `root/registry.csv`, and returns the token `record_trials` needs. An overlapping out-of-sample window from any
    earlier registration is recorded under `registration.oos_reuse` (not hashed) and returned for the report; it never blocks."""
    h = hash_for(kind, spec)
    if spec.get("spec_hash") not in (None, h):
        raise RegistrationError(f"the spec says its hash is {spec['spec_hash']}, but it hashes to {h}")
    f = resolve_fields(kind, spec, fields)
    root, out_dir = Path(root), Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).isoformat(sep=" ", timespec="microseconds")
    reuse = tuple(reuse_lines(f["oos_start"], f["oos_end"], root, h))            # read the ledger BEFORE adding this row
    block = {"registered_at": stamp, "kind": kind, **{k: f[k] for k in REQUIRED if k not in ("hypothesis", "pass_fail")},
             "registry": REGISTRY_FILE, "oos_reuse": list(reuse)}
    spec_file = out_dir / f"spec_{h}.json"
    if not spec_file.exists():                                                  # never overwrite an earlier registration's file
        with spec_file.open("x", encoding="utf-8") as fh:
            fh.write(json.dumps({**spec, "spec_hash": h, "registration": block}, indent=2, default=str))
    _append_registry(root, {"registered_at": stamp, "kind": kind, "family_id": f["family_id"], "spec_hash": h, "source": "registered",
                            "split_cutoff": f["split_cutoff"], "oos_start": f["oos_start"], "oos_end": f["oos_end"],
                            "horizons": f["horizons"], "raw_sha256": f["raw_sha256"], "planned_cells": f["planned_cells"], "note": ""})
    token = secrets.token_hex(16)
    _ISSUED[token] = 0
    return Registration(kind, f["family_id"], h, stamp, root, spec_file, int(f["planned_cells"]), f["oos_start"], f["oos_end"],
                        "registered", reuse, token)


def registration_block(reg: Registration) -> dict:
    """The not-hashed block a runner may add to its own copy of the spec (spec.json, spec_features.json)."""
    return {"registered_at": reg.registered_at, "kind": reg.kind, "family_id": reg.family_id, "oos_start": reg.oos_start,
            "oos_end": reg.oos_end, "planned_cells": reg.planned_cells, "registry": REGISTRY_FILE, "oos_reuse": list(reg.oos_reuse)}


def _set_aside_if_other_layout(path: Path, cols: list[str]) -> None:
    if path.exists() and path.read_text(encoding="utf-8").splitlines()[:1] != [",".join(cols)]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")                      # never mix two column layouts in one file
        path.rename(path.with_name(f"{path.stem}_older_layout_{stamp}{path.suffix}"))


def _append_rows(path: Path, cols: list[str], rows: list[list]) -> None:
    _set_aside_if_other_layout(path, cols)
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        if new:
            w.writerow(cols)
        w.writerows(rows)


def _append_registry(root: Path, row: dict) -> None:
    _append_rows(Path(root) / REGISTRY_FILE, REGISTRY_COLS, [[row.get(c, "") for c in REGISTRY_COLS]])


def read_registry(root: Path | str) -> pd.DataFrame:
    p = Path(root) / REGISTRY_FILE
    if not p.exists():
        return pd.DataFrame(columns=REGISTRY_COLS)
    return pd.read_csv(p, dtype=str, keep_default_na=False)


# ---------------------------------------------------------------- period ledger
def _ts(v) -> pd.Timestamp | None:
    return pd.Timestamp(v) if isinstance(v, str) and v.strip() else None


def periods_viewed(oos_start: str, oos_end: str, root: Path | str) -> pd.DataFrame:
    """Every registration (any kind) whose out-of-sample window overlaps [oos_start, oos_end]. A registration with a missing
    window end is treated as open on that side (conservative): a backfilled row whose window is unknown counts as overlapping.
    Adds a column `window_known`."""
    reg = read_registry(root)
    if reg.empty:
        return reg.assign(window_known=pd.Series(dtype=bool))
    a, b = pd.Timestamp(oos_start), pd.Timestamp(oos_end)
    keep, known = [], []
    for _, r in reg.iterrows():
        s, e = _ts(r["oos_start"]), _ts(r["oos_end"])
        keep.append((s is None or s <= b) and (e is None or e >= a))
        known.append(s is not None and e is not None)
    return reg.assign(window_known=known)[keep].reset_index(drop=True)


def reuse_lines(oos_start: str, oos_end: str, root: Path | str, current_hash: str) -> list[str]:
    """Plain sentences about earlier looks at this out-of-sample window. Empty list if there were none."""
    seen = periods_viewed(oos_start, oos_end, root)
    if seen.empty:
        return []
    out = []
    same = seen[seen["spec_hash"] == current_hash]
    other = seen[(seen["spec_hash"] != current_hash) & seen["window_known"]]
    unknown = seen[(seen["spec_hash"] != current_hash) & ~seen["window_known"]]
    if len(other):
        firsts = other.sort_values("registered_at").drop_duplicates("spec_hash")
        items = [f"{r['kind']} spec `{r['spec_hash']}` (first registered {r['registered_at'][:10]}, window {r['oos_start']} to {r['oos_end']})"
                 for _, r in firsts.head(6).iterrows()]
        more = f" and {len(firsts) - 6} more" if len(firsts) > 6 else ""
        out.append(f"This out-of-sample window ({oos_start} to {oos_end}) overlaps one already used by {len(firsts)} earlier "
                   f"spec{'s' if len(firsts) != 1 else ''} in `{REGISTRY_FILE}`: {'; '.join(items)}{more}. "
                   "Those results were seen before this registration, so this period is not untouched for this question.")
    if len(unknown):
        hs = ", ".join(f"`{h}`" for h in dict.fromkeys(unknown["spec_hash"]))
        out.append(f"{unknown['spec_hash'].nunique()} earlier registration{'s' if unknown['spec_hash'].nunique() != 1 else ''} ({hs}) "
                   "have no recorded window and may overlap this one.")
    if len(same):
        out.append(f"This same spec was registered {len(same)} time{'s' if len(same) != 1 else ''} before (re-runs of an unchanged spec).")
    return out


def earlier_specs(kind: str, root: Path | str, exclude: str | None = None, before: str | None = None) -> list[str]:
    """Distinct spec hashes of this kind in registration order (crashed runs included: they registered before computing).
    `before` keeps only registrations strictly earlier than that timestamp; `exclude` drops one hash (usually the current one)."""
    _check_kind(kind)
    reg = read_registry(root)
    reg = reg[reg["kind"] == kind]
    if reg.empty:
        return []
    t = pd.to_datetime(reg["registered_at"], format="mixed")
    reg = reg.assign(_t=t).sort_values("_t", kind="stable")
    if before is not None:
        reg = reg[reg["_t"] < pd.Timestamp(before)]
    return [h for h in dict.fromkeys(reg["spec_hash"]) if h != exclude]


# ---------------------------------------------------------------- trial log
def _valid(reg) -> bool:
    if not isinstance(reg, Registration) or reg._token not in _ISSUED:
        return False
    if reg.source == "registered" and (reg.spec_file is None or not Path(reg.spec_file).exists()):
        return False
    rows = read_registry(reg.root)
    return bool(((rows["spec_hash"] == reg.spec_hash) & (rows["registered_at"] == reg.registered_at)).any())


def _is_true(v) -> bool:
    return v is True or (isinstance(v, (bool, int)) and bool(v)) or str(v).strip().lower() == "true"


def record_trials(reg: Registration, rows: pd.DataFrame, run_at: str | None = None) -> int:
    """Append every computed cell to `trials_all.csv` under one registration. The only writer of the trial log.

    rows: columns cell, stat, group, period, horizon, n, estimate, and optionally lo, hi, p_raw, p_holm, primary. If rows carry
    spec_hash / kind / family_id columns, they must match the registration. Refuses: no token, more cells than planned.
    Backfilled registrations keep each row's own run_at; new runs get one run_at for all rows."""
    if not _valid(reg):
        raise RegistrationError("record_trials needs a Registration returned by registry.register() whose spec file and registry row "
                                "exist. Register the spec before computing anything.")
    rows = pd.DataFrame(rows).copy()
    for key in ("spec_hash", "kind", "family_id"):
        if key in rows.columns and (rows[key].astype(str) != str(getattr(reg, key))).any():
            raise RegistrationError(f"trial rows carry a {key} that differs from the registration ({getattr(reg, key)})")
    need = ["cell", "stat", "group", "period", "horizon", "n", "estimate"]
    if missing := [c for c in need if c not in rows.columns]:
        raise RegistrationError(f"trial rows lack columns: {missing}")
    done = _ISSUED[reg._token]
    if reg.planned_cells is not None and done + len(rows) > reg.planned_cells:
        raise RegistrationError(f"{done + len(rows)} trial cells for spec {reg.spec_hash}, but only {reg.planned_cells} were planned")
    stamp = run_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    out = []
    for _, r in rows.iterrows():
        when = r["run_at"] if reg.source == "backfilled" and "run_at" in rows.columns else stamp
        n = r["n"]
        out.append([when, reg.kind, reg.family_id, reg.spec_hash, r["cell"], r["stat"], r["group"], r["period"],
                    "" if pd.isna(r["horizon"]) else int(r["horizon"]), 0 if pd.isna(n) else int(n),
                    *(_num(r.get(c)) for c in ("estimate", "lo", "hi", "p_raw", "p_holm")), _is_true(r.get("primary", False))])
    _append_rows(reg.trials_path, TRIAL_COLS, out)
    _ISSUED[reg._token] = done + len(out)
    return len(out)


def _num(v) -> str:
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    return "" if math.isnan(f) else f"{f:.6f}"


def read_trials(root: Path | str) -> pd.DataFrame:
    p = Path(root) / TRIALS_FILE
    if not p.exists():
        return pd.DataFrame(columns=TRIAL_COLS)
    df = pd.read_csv(p, dtype={"spec_hash": str, "family_id": str, "run_at": str})
    df["primary"] = df["primary"].astype(str).str.lower() == "true"
    return df


def cells_per_run(root: Path | str) -> pd.DataFrame:
    """Logged cells per (kind, spec, run) next to the planned count from the registry (backfilled runs have no plan)."""
    t, reg = read_trials(root), read_registry(root)
    if t.empty:
        return pd.DataFrame(columns=["kind", "family_id", "spec_hash", "run_at", "logged", "planned_cells"])
    got = t.groupby(["kind", "family_id", "spec_hash", "run_at"]).size().rename("logged").reset_index()
    plan = reg[reg["source"] == "registered"].drop_duplicates("spec_hash", keep="last")[["spec_hash", "planned_cells"]]
    return got.merge(plan, on="spec_hash", how="left")


# ---------------------------------------------------------------- one-off backfill of the older per-runner logs
LEGACY = {
    "backtest": ["run_at", "spec_hash", "variant", "horizon", "group", "period", "n", "ex_own", "ex_own_lo", "ex_own_hi", "primary"],
    "backtest_nogroup": ["run_at", "spec_hash", "variant", "horizon", "period", "n", "ex_own", "ex_own_lo", "ex_own_hi", "primary"],
    "features": ["run_at", "family_id", "spec_hash", "feature", "stat", "group", "period", "horizon", "n", "estimate", "lo", "hi",
                 "p_raw", "p_holm", "sign_is"],
}
BACKTEST_FAMILY = "backtest_dip_rule"


def backfill_registration(kind: str, spec_hash_: str, root: Path | str, family_id: str, registered_at: str, note: str,
                          window: dict | None = None) -> Registration:
    """A registry row for a spec that was run before the registry existed, marked source=backfilled. It records that the
    registration came late; it does not pretend the spec was registered before its results were seen."""
    _check_kind(kind)
    w = window or {}
    _append_registry(Path(root), {"registered_at": registered_at, "kind": kind, "family_id": family_id, "spec_hash": spec_hash_,
                                  "source": "backfilled", **{k: w.get(k, "") for k in ("split_cutoff", "oos_start", "oos_end", "horizons",
                                                                                         "raw_sha256", "planned_cells")}, "note": note})
    token = secrets.token_hex(16)
    _ISSUED[token] = 0
    return Registration(kind, family_id, spec_hash_, registered_at, Path(root), None, None, w.get("oos_start", ""), w.get("oos_end", ""),
                        "backfilled", (), token)


def _legacy_layout(path: Path) -> str | None:
    head = path.read_text(encoding="utf-8").splitlines()[:1]
    for name, cols in LEGACY.items():
        if head == [",".join(cols)]:
            return name
    return None


def _window_from_specs(root: Path, h: str) -> dict:
    """Split and window for an old spec if a spec file with that hash is still on disk (spec_<hash>.json, spec.json, spec_features.json)."""
    for p in sorted(root.rglob("spec*.json")):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if s.get("spec_hash") != h:
            continue
        cut = _get(s, "split.cutoff") or _get(s, "split.cutoff_last_in_sample_date")
        w = {"split_cutoff": cut or "", "raw_sha256": _get(s, "data.raw_sha256") or _get(s, "parent_backtest_spec.raw_sha256") or ""}
        if cut:                                                # the window is (cutoff, last bar]; the day after the cutoff is a safe start
            w["oos_start"] = str((pd.Timestamp(cut) + pd.Timedelta(days=1)).date())
        if last := _get(s, "data.last_bar"):
            w["oos_end"] = str(last)
        if hz := s.get("horizons"):
            w["horizons"] = ";".join(str(int(x)) for x in hz)
        return w
    return {}


def backfill(root: Path | str, files: list[Path] | None = None) -> list[str]:
    """Import the hashes (into registry.csv, source=backfilled) and the trial rows (into trials_all.csv) of the older logs, once.
    A hash already backfilled from the same file is skipped, so running this twice adds nothing. Returns one line per action."""
    root = Path(root)
    files = files or [p for p in (root / "trials.csv", root / "trials_features.csv", *sorted(root.glob("trials_older_layout_*.csv")),
                                  *sorted(root.glob("trials_features_older_layout_*.csv"))) if p.exists()]
    done = read_registry(root)
    done = done[done["source"] == "backfilled"]
    log = []
    for path in files:
        layout = _legacy_layout(path)
        if layout is None:
            log.append(f"skip {path.name}: unknown layout")
            continue
        df = pd.read_csv(path, dtype={"spec_hash": str, "run_at": str})
        for h, g in df.groupby("spec_hash", sort=False):
            tag = f"backfilled from {path.name}"
            if ((done["spec_hash"] == h) & (done["note"].str.startswith(tag))).any():
                log.append(f"skip {h}: already {tag}")
                continue
            kind = "features" if layout == "features" else "backtest"
            fam = str(g["family_id"].iloc[0]) if layout == "features" else BACKTEST_FAMILY
            first = str(min(pd.to_datetime(g["run_at"]))).replace("T", " ")
            note = f"{tag}; first run {g['run_at'].iloc[0]}; registered after its results were seen"
            reg = backfill_registration(kind, h, root, fam, first, note, _window_from_specs(root, h))
            if layout == "features":
                rows = g.rename(columns={"feature": "cell", "estimate": "estimate"})
                rows["primary"] = (rows["stat"] == "spearman") & (rows["period"] == "OOS") & (rows["group"] == "All")
            else:
                rows = g.rename(columns={"variant": "cell", "ex_own": "estimate", "ex_own_lo": "lo", "ex_own_hi": "hi"})
                rows["stat"] = "ex_own"
                if "group" not in rows.columns:
                    rows["group"] = ""
                rows["primary"] = rows["primary"].astype(str).str.lower() == "true"
            n = record_trials(reg, rows.drop(columns=["spec_hash", "family_id"], errors="ignore"))
            log.append(f"{h}: {kind}, {n} trial rows imported from {path.name} (marked backfilled)")
    return log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dipdash.registry", description="Registry maintenance.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="import the older trials.csv / trials_features.csv once (the old files are not changed)")
    b.add_argument("--root", default="output/backtests")
    b.add_argument("files", nargs="*", type=Path)
    a = ap.parse_args(argv)
    for line in backfill(Path(a.root), a.files or None):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
