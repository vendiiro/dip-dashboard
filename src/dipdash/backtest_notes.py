"""Human-written notes about specific backtest runs, keyed by spec hash.

Why a separate file: the report must not carry sentences that were true for one run and silently appear in the next one.
A note is attached to the spec hash it was written for. A spec without a note gets "No review is recorded for spec X", and
never inherits another spec's review. Notes are descriptive only: they are NOT part of the spec hash (see freeze_spec), so
editing a note never changes the identity of the analysis.

Numbers quoted inside a note are also stored under "quoted" so a test (and the report) can check them against the run.
"""
from __future__ import annotations

REVIEWED_SPEC = "79288caaa97d33b1"

NOTES: dict[str, dict] = {
    REVIEWED_SPEC: {
        "revisions": [
            "Run 1 (spec 90205cfc6da3a007) was a full run that included the out-of-sample primary cell, so the freeze is 'before the first run', not before anyone saw a number. "
            "Its spec file was overwritten by the next run (only the hash survives in trials.csv); specs are now archived by hash.",
            "Placebo: the independent same-stock same-year draw ignores that events share dates and gave p = 0.002 beside an interval that included zero. "
            "A date-shift placebo that moves all events by one common lag replaced it; the independent one stays in results.csv as 'placebo_*'. This lowered significance.",
            "Baseline and placebo days must have a computable signal (252 bars of history); before, a stock's first year counted as 'non-dip'. No predictable direction; the primary cell did not move.",
            "92 zero-volume bars were removed before the run (91 exchange-holiday placeholders and one corrupt price). They were all in sample.",
            "Later runs with the same analysis (same numbers) only changed report charts and wording, so trials.csv shows several runs per spec.",
            "Found by the independent review and NOT acted on in the numbers: one more bad price (KNEBV.HE 2025-07-29) creates one false out-of-sample event; "
            "removing it moves the primary excess from +0.2660% to +0.2667%.",
        ],
        "review": (
            "A separate reviewer that did not write the code recomputed the signals, cooldown events (5 tickers), 20 forward returns and the primary cell from the raw prices "
            "without using this code. It reported no look-ahead and no mismatch, and the same verdict (interval includes zero) under wider bootstrap blocks. Its other points are "
            "reflected in this report: the index column's dividend mismatch, that survivorship still biases the own-days comparison, one bad price the validators missed "
            "(KNEBV.HE 2025-07-29: +29.6%, then −24.1%, on low volume; it creates one false out-of-sample event and moves the primary excess from +0.2660% to +0.2667%, "
            "and a spike-and-revert check now flags such bars), and the in-sample interval's lower bound being −0.03%, not zero."
        ),
        "data_notes": [
            "One of the removed zero-volume bars was a corrupt price (NOVO-B.CO, 2010-05-14: price doubled, volume 0); the rest are exchange-holiday placeholder rows with an unchanged price.",
        ],
        # figures the texts above quote; checked against the run by the report and the tests
        "quoted": {"primary_ex_own": 0.002660, "primary_n": 1504, "primary_ex_own_without_knebv_event": 0.002667},
    },
}


def notes_for(spec_hash: str) -> dict:
    """The notes written for exactly this spec hash, or {} (never another spec's notes)."""
    return NOTES.get(spec_hash, {})


def revisions_for(spec_hash: str) -> list[str]:
    return list(notes_for(spec_hash).get("revisions", []))


def quoted_mismatch(spec_hash: str, primary_ex_own: float | None, primary_n: int | None) -> str:
    """Empty string if the figures a note quotes agree with this run's primary cell; otherwise a one-line warning."""
    q = notes_for(spec_hash).get("quoted")
    if not q:
        return ""
    if primary_ex_own is None or primary_n is None:
        return "The recorded notes quote a result for the main question, but this run has no result for it to compare with."
    if abs(q["primary_ex_own"] - primary_ex_own) > 5e-7 or q["primary_n"] != primary_n:
        return (f"The recorded notes quote a result for the main question of {q['primary_ex_own']:+.4%} (n = {q['primary_n']:,}); this run gives "
                f"{primary_ex_own:+.4%} (n = {primary_n:,}). Read the notes with that difference in mind.")
    return ""
