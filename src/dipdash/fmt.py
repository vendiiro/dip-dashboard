"""Plain-text number formatting shared by the backtest report and the daily digest. No heavy imports."""
from __future__ import annotations

import numpy as np


def pct(x, d: int = 1, sign: bool = True) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    s = f"{abs(x) * 100:.{d}f}%"
    if round(abs(x) * 100, d) == 0:
        return s                                   # never print "−0.0%"
    return ("−" if x < 0 else ("+" if sign and x > 0 else "")) + s


def bound(x) -> str:
    """A bound of an interval. Near zero it gets 2 decimals and its sign, so '0.0%' cannot hide that an interval includes zero."""
    if round(abs(x) * 100, 1) == 0:
        return ("−" if x < 0 else "+") + f"{abs(x) * 100:.2f}%"
    return pct(x)


def interval(lo, hi) -> str:
    return "n/a" if lo is None or not np.isfinite(lo) else f"{bound(lo)} to {bound(hi)}"


def md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)
