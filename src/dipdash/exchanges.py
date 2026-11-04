"""One registry of exchanges, keyed by Yahoo ticker suffix. Leaf module: imports nothing from dipdash.

Replaces three hand-kept tables (currency in validate.py, time zone in earnings.py, Nordic OpenBB suffixes in
openbb_source.py); those names are now views derived from EXCHANGES. Close times are regular session ends in local
time and are NOT verified against the exchanges (nothing reads them yet)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class Exchange:
    suffix: str            # Yahoo suffix including the dot; "" = US (no suffix)
    name: str
    tz: str                # IANA zone of the exchange
    close: time            # regular session end, local time (unverified)
    currency: str | None   # trading currency; None = not settled (.L: pounds vs pence)
    openbb: str | None     # OpenBB provider that serves the line, or None
    index: str | None      # Yahoo symbol of the country index, or None (falls back to the regional index)


def _x(suffix, name, tz, hh, mm, ccy, openbb=None, index=None) -> Exchange:
    return Exchange(suffix, name, tz, time(hh, mm), ccy, openbb, index)


EXCHANGES: dict[str, Exchange] = {e.suffix: e for e in (
    _x("", "NYSE/Nasdaq", "America/New_York", 16, 0, "USD", "nasdaq", "^GSPC"),
    _x(".PA", "Euronext Paris", "Europe/Paris", 17, 30, "EUR", index="^FCHI"),
    _x(".DE", "Xetra", "Europe/Berlin", 17, 30, "EUR", index="^GDAXI"),
    _x(".ST", "Nasdaq Stockholm", "Europe/Stockholm", 17, 30, "SEK", "nasdaq_nordic", "^OMXSPI"),
    _x(".SW", "SIX Swiss Exchange", "Europe/Zurich", 17, 30, "CHF", index="^SSMI"),
    _x(".HE", "Nasdaq Helsinki", "Europe/Helsinki", 18, 30, "EUR", "nasdaq_nordic", "^OMXH25"),
    _x(".MI", "Borsa Italiana", "Europe/Rome", 17, 30, "EUR"),
    _x(".AS", "Euronext Amsterdam", "Europe/Amsterdam", 17, 30, "EUR", index="^AEX"),
    _x(".MC", "BME Madrid", "Europe/Madrid", 17, 30, "EUR"),
    _x(".CO", "Nasdaq Copenhagen", "Europe/Copenhagen", 17, 0, "DKK", "nasdaq_nordic", "^OMXC25"),
    _x(".OL", "Oslo Bors", "Europe/Oslo", 16, 20, "NOK", index="OSEBX.OL"),
    _x(".BR", "Euronext Brussels", "Europe/Brussels", 17, 30, "EUR"),
    _x(".LS", "Euronext Lisbon", "Europe/Lisbon", 16, 30, "EUR"),
    _x(".L", "London Stock Exchange", "Europe/London", 16, 30, None),
)}


def suffix_of(ticker: str) -> str:
    """'.HE' for 'NOKIA.HE'; '' for tickers without a dot (US lines, including share classes like BRK-B)."""
    return "." + ticker.rsplit(".", 1)[1].upper() if "." in ticker else ""


def exchange_for(ticker: str) -> Exchange | None:
    """The registry entry for a ticker, or None when its suffix is unknown."""
    return EXCHANGES.get(suffix_of(ticker))
