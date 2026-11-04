"""Settings (config/settings.toml) and universe (config/universe.csv) loading."""
from __future__ import annotations

import csv
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


@dataclass(frozen=True)
class DipSettings:
    drop_1d: float = 0.04
    drop_5d: float = 0.07
    drawdown_20d: float = 0.12


@dataclass(frozen=True)
class QualitySettings:
    min_score: int = 60
    roe_min: float = 0.12
    margin_min: float = 0.08
    debt_to_equity_max: float = 150
    market_cap_min: float = 20_000_000_000


@dataclass(frozen=True)
class FallingKnifeSettings:
    below_200d_falling: bool = True
    drawdown_52w: float = 0.35


@dataclass(frozen=True)
class NewsSettings:
    fetch_if_5d_drop: float = 0.05


@dataclass(frozen=True)
class BacktestSettings:
    horizons: tuple[int, ...] = (5, 21, 63)
    cooldown_days: int = 21
    cost_roundtrip: float = 0.001
    oos_fraction: float = 0.4
    start_date: str = "2010-01-01"       # first signal date; earlier bars are only warm-up for the 252-day inputs
    stress_drawdown: float = 0.10        # "market stress" = regional index this far below its trailing high
    stress_window: int = 60              # trailing window (bars) for that high
    ci_level: float = 0.90
    bootstrap_draws: int = 5000
    placebo_draws: int = 2000
    seed: int = 20261102


@dataclass(frozen=True)
class ScheduleSettings:
    timezone: str = "Europe/Helsinki"
    run_time: str = "00:15"


@dataclass(frozen=True)
class DataSettings:
    max_stale_trading_days: int = 4
    min_screened_fraction: float = 0.9       # a run that screens fewer stocks than this share of the universe fails and keeps yesterday's files


@dataclass(frozen=True)
class EarningsSettings:
    recent_days: int = 5     # "reported recently": last report within this many trading days up to the data date
    soon_days: int = 10      # "reports soon": next report within this many trading days after the data date


@dataclass(frozen=True)
class IndexSpec:
    symbol: str
    name: str
    region: str     # the universe region this index is the market context for
    suffixes: tuple[str, ...] = ()   # optional: ticker suffixes (".ST") this index is the country-level context for; wins over `region`


DEFAULT_INDICES = (IndexSpec("^GSPC", "S&P 500", "US"), IndexSpec("^STOXX", "STOXX 600", "Europe"),
                   IndexSpec("^OMXH25", "OMX Helsinki 25", "Nordic", (".HE",)))

DEFAULT_COUNTRY_INDICES = (
    IndexSpec("^OMXSPI", "OMX Stockholm All-Share", "Nordic", (".ST",)),
    IndexSpec("^OMXC25", "OMX Copenhagen 25", "Nordic", (".CO",)),
    IndexSpec("OSEBX.OL", "Oslo Bors All-Share", "Nordic", (".OL",)),
    IndexSpec("^AEX", "AEX", "Europe", (".AS",)),
    IndexSpec("^GDAXI", "DAX (total return)", "Europe", (".DE",)),
    IndexSpec("^FCHI", "CAC 40", "Europe", (".PA",)),
    IndexSpec("^SSMI", "SMI", "Europe", (".SW",)),
)


@dataclass(frozen=True)
class ContextSettings:
    """How a stock is matched to a market-context index: ticker suffix, then region, then this fallback region."""
    fallback_region: str = "Europe"      # non-US stock with no country or region index: compare with the index of this region


@dataclass(frozen=True)
class Settings:
    dip: DipSettings = field(default_factory=DipSettings)
    quality: QualitySettings = field(default_factory=QualitySettings)
    falling_knife: FallingKnifeSettings = field(default_factory=FallingKnifeSettings)
    news: NewsSettings = field(default_factory=NewsSettings)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)
    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    data: DataSettings = field(default_factory=DataSettings)
    earnings: EarningsSettings = field(default_factory=EarningsSettings)
    indices: tuple[IndexSpec, ...] = DEFAULT_INDICES
    country_indices: tuple[IndexSpec, ...] = DEFAULT_COUNTRY_INDICES   # extra per-country indices ([[country_indices]]); same fields as [[indices]]
    context: ContextSettings = field(default_factory=ContextSettings)

    @property
    def all_indices(self) -> tuple[IndexSpec, ...]:
        """Every index to fetch: the region ones, then the country ones."""
        return self.indices + self.country_indices


@dataclass(frozen=True)
class Stock:
    ticker: str
    name: str
    region: str
    sector: str = ""


def _section(cls, raw: dict, name: str):
    known = {f.name for f in fields(cls)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"settings.toml [{name}]: unknown key(s) {sorted(unknown)}; expected {sorted(known)}")
    kw = {k: tuple(v) if isinstance(v, list) else v for k, v in raw.items()}
    return cls(**kw)


def load_settings(path: Path | str | None = None) -> Settings:
    """Read settings.toml. A missing section or key falls back to the default above."""
    p = Path(path) if path else CONFIG_DIR / "settings.toml"
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    unknown = set(raw) - {f.name for f in fields(Settings)}
    if unknown:
        raise ValueError(f"settings.toml: unknown section(s) {sorted(unknown)}")
    defaults = Settings()
    sections = {f.name: _section(type(getattr(defaults, f.name)), raw.get(f.name, {}), f.name)
                for f in fields(Settings) if f.name not in ("indices", "country_indices")}
    indices = tuple(_section(IndexSpec, i, "indices") for i in raw["indices"]) if "indices" in raw else DEFAULT_INDICES
    country = tuple(_section(IndexSpec, i, "country_indices") for i in raw["country_indices"]) if "country_indices" in raw else DEFAULT_COUNTRY_INDICES
    return Settings(**sections, indices=indices, country_indices=country)


def load_universe(path: Path | str | None = None) -> list[Stock]:
    """Read universe.csv. Only `ticker` is required; name defaults to the ticker, region to 'Other'."""
    p = Path(path) if path else CONFIG_DIR / "universe.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "ticker" not in reader.fieldnames:
            raise ValueError(f"{p}: needs a 'ticker' column")
        out, seen = [], set()
        for i, r in enumerate(reader, start=2):
            t = (r.get("ticker") or "").strip()
            if not t:
                raise ValueError(f"{p} line {i}: empty ticker")
            if t in seen:
                raise ValueError(f"{p} line {i}: duplicate ticker {t}")
            seen.add(t)
            out.append(Stock(t, (r.get("name") or t).strip(), (r.get("region") or "Other").strip(),
                             (r.get("sector") or "").strip()))
    return out
