from datetime import date

import itertools

import pytest

from dipdash.config import DipSettings, FallingKnifeSettings, NewsSettings, QualitySettings, Settings
from dipdash.screen import (FALLING_KNIFE, LOW_QUALITY, NO_DIP, NO_FUNDAMENTALS, QUALITY_DIP, classify, classify_prev,
                            dip_reasons, is_dip, is_falling_knife, is_stale, needs_news, setup_label, setup_text, trading_days_old)

DIP, KNIFE, NEWS, S = DipSettings(), FallingKnifeSettings(), NewsSettings(), Settings()


def m(**kw):
    base = {"r1": 0.0, "r5": 0.0, "dd20": 0.0, "vs200": 0.05, "dd52": -0.05, "s200_falling": False}
    return {**base, **kw}


# ---- dip -------------------------------------------------------------------
@pytest.mark.parametrize("key, limit", [("r1", -0.04), ("r5", -0.07), ("dd20", -0.12)])
def test_each_dip_rule_triggers_alone_at_its_limit(key, limit):
    assert is_dip(m(**{key: limit}), DIP)
    assert not is_dip(m(**{key: limit + 0.0001}), DIP)


def test_no_dip_when_nothing_fell():
    assert dip_reasons(m(), DIP) == []


def test_reasons_name_every_rule_that_fired():
    why = dip_reasons(m(r1=-0.05, r5=-0.08), DIP)
    assert len(why) == 2 and "1-day" in why[0] and "5-day" in why[1]


def test_missing_metrics_never_count_as_a_dip():
    assert not is_dip(m(r1=None, r5=None, dd20=None), DIP)


def test_dip_limits_come_from_settings():
    assert is_dip(m(r1=-0.03), DipSettings(drop_1d=0.03))


# ---- falling knife ---------------------------------------------------------
def test_knife_needs_all_three_conditions():
    base = m(vs200=-0.1, s200_falling=True, dd52=-0.40)
    assert is_falling_knife(base, KNIFE)
    assert not is_falling_knife({**base, "vs200": 0.01}, KNIFE)
    assert not is_falling_knife({**base, "s200_falling": False}, KNIFE)
    assert not is_falling_knife({**base, "dd52": -0.30}, KNIFE)


def test_knife_boundary_at_35_percent():
    assert is_falling_knife(m(vs200=-0.1, s200_falling=True, dd52=-0.35), KNIFE)
    assert not is_falling_knife(m(vs200=-0.1, s200_falling=True, dd52=-0.3499), KNIFE)


def test_exactly_on_the_200_day_average_is_not_below_it():
    assert not is_falling_knife(m(vs200=0.0, s200_falling=True, dd52=-0.5), KNIFE)


def test_slope_condition_can_be_switched_off():
    k = FallingKnifeSettings(below_200d_falling=False)
    assert is_falling_knife(m(vs200=-0.1, s200_falling=False, dd52=-0.5), k)


def test_knife_is_false_when_metrics_are_missing():
    assert not is_falling_knife(m(vs200=None, dd52=-0.5, s200_falling=True), KNIFE)
    assert not is_falling_knife(m(vs200=-0.1, dd52=None, s200_falling=True), KNIFE)


# ---- setup label -----------------------------------------------------------
DIPPED = m(r5=-0.10)


def test_not_a_dip_stays_no_dip_whatever_the_quality():
    assert classify(m(), 100, S) == NO_DIP


def test_quality_dip_and_min_score_boundary():
    assert classify(DIPPED, S.quality.min_score, S) == QUALITY_DIP
    assert classify(DIPPED, S.quality.min_score - 1, S) == LOW_QUALITY


def test_missing_fundamentals_never_count_as_quality():
    assert classify(DIPPED, None, S) == NO_FUNDAMENTALS


def test_falling_knife_outranks_quality():
    knife = m(r5=-0.10, vs200=-0.2, s200_falling=True, dd52=-0.5)
    assert classify(knife, 100, S) == FALLING_KNIFE


def test_min_score_comes_from_settings():
    strict = Settings(quality=QualitySettings(min_score=90))
    assert classify(DIPPED, 80, strict) == LOW_QUALITY


# ---- one setup label, shared by classify and classify_prev ------------------
QS = [None, 0, 59, 60, 100]


def expected_label(dip, knife, q):
    if not dip:
        return NO_DIP
    if knife:
        return FALLING_KNIFE
    if q is None:
        return NO_FUNDAMENTALS
    return QUALITY_DIP if q >= 60 else LOW_QUALITY


@pytest.mark.parametrize("dip, knife, q", list(itertools.product([False, True], [False, True], QS)))
def test_setup_label_truth_table(dip, knife, q):
    assert setup_label(dip, knife, q, S) == expected_label(dip, knife, q)   # q = 0 is a score, not "missing"


@pytest.mark.parametrize("dip, knife, q", list(itertools.product([False, True], [False, True], QS)))
def test_classify_and_classify_prev_agree(dip, knife, q):
    metrics = m(r1=-0.05 if dip else 0.0, vs200=-0.1 if knife else 0.05,
                dd52=-0.5 if knife else -0.05, s200_falling=knife)
    want = expected_label(dip, knife, q)
    assert classify(metrics, q, S) == want
    assert classify_prev({"dip": dip, "knife": knife}, q, S) == want


def test_classify_prev_without_previous_data_is_none():
    assert classify_prev(None, 80, S) is None
    assert classify_prev({}, 80, S) is None


def test_setup_label_respects_a_custom_min_score():
    strict = Settings(quality=QualitySettings(min_score=90))
    assert setup_label(True, False, 80, strict) == LOW_QUALITY
    assert classify_prev({"dip": True, "knife": False}, 90, strict) == QUALITY_DIP


# ---- news selection --------------------------------------------------------
@pytest.mark.parametrize("kw, expected", [
    ({"r5": -0.05}, True), ({"r5": -0.049}, False),
    ({"r1": -0.025}, True), ({"r1": -0.02}, False),
    ({"dd20": -0.10}, True), ({"dd20": -0.09}, False),
    ({}, False),
])
def test_needs_news_thresholds(kw, expected):
    assert needs_news(kw, NEWS) is expected


def test_needs_news_tolerates_none():
    assert needs_news({"r5": None, "r1": None, "dd20": None}, NEWS) is False


# ---- stale bars (today = Monday 2026-11-02) --------------------------------
TODAY = date(2026, 11, 2)


@pytest.mark.parametrize("last_bar, age", [
    (date(2026, 10, 30), 1),   # Friday
    (date(2026, 10, 29), 2),
    (date(2026, 10, 27), 4),
    (date(2026, 10, 26), 5),
])
def test_trading_days_old(last_bar, age):
    assert trading_days_old(last_bar, TODAY) == age


def test_stale_means_strictly_older_than_the_limit():
    assert not is_stale(date(2026, 10, 27), TODAY, 4)   # exactly 4 days old
    assert is_stale(date(2026, 10, 26), TODAY, 4)       # 5 days old


def test_a_weekend_run_is_not_stale_for_friday_bars():
    assert not is_stale(date(2026, 10, 30), date(2026, 11, 1), 4)


# ---- RES-2: must-pass and distorted fundamentals --------------------------------
@pytest.mark.parametrize("dip, knife, q", list(itertools.product([False, True], [False, True], QS)))
def test_truth_table_with_q_ok_true_is_unchanged_and_false_only_demotes_quality(dip, knife, q):
    assert setup_label(dip, knife, q, S, q_ok=True) == expected_label(dip, knife, q)
    want = expected_label(dip, knife, q)
    assert setup_label(dip, knife, q, S, q_ok=False) == (LOW_QUALITY if want == QUALITY_DIP else want)


@pytest.mark.parametrize("dip, knife, q", list(itertools.product([False, True], [False, True], QS)))
@pytest.mark.parametrize("q_ok", [True, False])
def test_distorted_only_changes_dips_with_a_score(dip, knife, q, q_ok):
    want = expected_label(dip, knife, q)
    got = setup_label(dip, knife, q, S, q_ok=q_ok, distorted=True)
    assert got == (NO_FUNDAMENTALS if want in (QUALITY_DIP, LOW_QUALITY) else want)


def test_distorted_outranks_a_failed_must_pass():
    assert setup_label(True, False, 100, S, q_ok=False, distorted=True) == NO_FUNDAMENTALS


def test_failed_must_pass_beats_a_high_score_and_knife_still_wins():
    assert setup_label(True, False, 100, S, q_ok=False) == LOW_QUALITY
    assert setup_label(True, True, 100, S, q_ok=False) == FALLING_KNIFE


def test_classify_and_classify_prev_take_the_flags():
    assert classify(DIPPED, 100, S, q_ok=False) == LOW_QUALITY
    assert classify(DIPPED, 100, S, distorted=True) == NO_FUNDAMENTALS
    assert classify_prev({"dip": True, "knife": False}, 100, S, q_ok=False) == LOW_QUALITY
    assert classify_prev({"dip": True, "knife": False}, 100, S, distorted=True) == NO_FUNDAMENTALS
    assert classify_prev({"dip": True, "knife": False}, 100, S) == QUALITY_DIP


def test_intc_like_end_to_end_label():
    from dipdash.quality import quality_detail
    good = {"returnOnEquity": 0.2, "profitMargins": 0.15, "debtToEquity": 80, "freeCashflow": 1e9,
            "revenueGrowth": 0.05, "marketCap": 1e11}
    r = quality_detail({**good, "profitMargins": -0.05}, S.quality)
    assert r.score >= S.quality.min_score
    assert classify(DIPPED, r.score, S, q_ok=not r.must_failed, distorted=r.status == "distorted") == LOW_QUALITY
    # must_pass = () reproduces today's label
    r0 = quality_detail({**good, "profitMargins": -0.05}, S.quality, must_pass=())
    assert classify(DIPPED, r0.score, S, q_ok=not r0.must_failed) == QUALITY_DIP


# ---- setup_text (RES-11) -----------------------------------------------------------
@pytest.mark.parametrize("setup, passed, applicable, text", [
    (QUALITY_DIP, 5, 6, "Dip · passes 5 of 6 scored checks"),
    (LOW_QUALITY, 2, 6, "Dip · passes 2 of 6 scored checks"),
    (QUALITY_DIP, 3, 4, "Dip · passes 3 of 4 scored checks"),   # Financials: 4 applicable
    (LOW_QUALITY, 0, 6, "Dip · passes 0 of 6 scored checks"),
    (NO_DIP, 5, 6, "No dip"),
    (FALLING_KNIFE, 5, 6, "Falling knife"),
    (NO_FUNDAMENTALS, None, None, "Dip, no fundamentals"),
    (NO_FUNDAMENTALS, 4, 6, "Dip, no fundamentals"),
    (QUALITY_DIP, None, None, "Dip"),
])
def test_setup_text(setup, passed, applicable, text):
    assert setup_text(setup, passed, applicable) == text


@pytest.mark.parametrize("setup, passed, applicable, scored, distorted, text", [
    (QUALITY_DIP, 3, 6, 4, False, "Dip · passes 3 of 4 scored checks (2 no data)"),
    (LOW_QUALITY, 1, 6, 5, False, "Dip · passes 1 of 5 scored checks (1 no data)"),
    (QUALITY_DIP, 3, 4, 4, False, "Dip · passes 3 of 4 scored checks"),
    (NO_FUNDAMENTALS, 3, 6, 6, True, "Dip · data looks unreliable"),
    (NO_FUNDAMENTALS, None, None, 0, False, "Dip, no fundamentals"),
    (NO_FUNDAMENTALS, 0, 6, 0, False, "Dip, no fundamentals"),
])
def test_setup_text_scored_denominator_and_distorted(setup, passed, applicable, scored, distorted, text):
    assert setup_text(setup, passed, applicable, scored, distorted) == text


def test_human_labels_are_neutral_and_low_label_distinguishable():
    from dipdash.screen import SETUP_LABELS
    assert SETUP_LABELS[LOW_QUALITY] == "Dip, fewer checks passed"
    assert set(SETUP_LABELS) == {NO_DIP, FALLING_KNIFE, NO_FUNDAMENTALS, QUALITY_DIP, LOW_QUALITY}
    assert not any("quality" in v.lower() for v in SETUP_LABELS.values())


def test_setup_text_unknown_label_raises_and_words_are_neutral():
    with pytest.raises(ValueError):
        setup_text("Strong buy", 5, 6)
    for lab in (QUALITY_DIP, LOW_QUALITY):
        assert "quality" not in setup_text(lab, 5, 6).lower()
