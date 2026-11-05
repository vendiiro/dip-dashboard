import pytest

from dipdash.config import QualitySettings
from dipdash.quality import build_checks, quality, quality_detail

Q = QualitySettings()
GOOD = {"returnOnEquity": 0.2, "profitMargins": 0.15, "debtToEquity": 80, "freeCashflow": 1e9,
        "revenueGrowth": 0.05, "marketCap": 1e11}


def test_all_checks_pass_scores_100():
    score, checks = quality(GOOD, Q)
    assert score == 100 and all(c["ok"] for c in checks)


def test_half_pass_scores_50():
    f = {**GOOD, "returnOnEquity": 0.01, "freeCashflow": -1, "revenueGrowth": -0.1}
    assert quality(f, Q)[0] == 50


@pytest.mark.parametrize("key, at_limit", [
    ("returnOnEquity", 0.12), ("profitMargins", 0.08), ("debtToEquity", 150), ("marketCap", 20_000_000_000),
])
def test_threshold_values_pass(key, at_limit):
    score, checks = quality({**GOOD, key: at_limit}, Q)
    assert score == 100


@pytest.mark.parametrize("key", ["freeCashflow", "revenueGrowth"])
def test_zero_is_not_positive(key):
    score, checks = quality({**GOOD, key: 0}, Q)
    assert score == 83  # 5 of 6


def test_missing_checks_are_excluded_not_failed():
    f = {k: GOOD[k] for k in ("returnOnEquity", "profitMargins", "debtToEquity", "freeCashflow")}
    score, checks = quality(f, Q)
    assert score == 100
    assert [c["ok"] for c in checks[-2:]] == [None, None]


def test_fewer_than_three_checks_with_data_gives_no_score():
    f = {"returnOnEquity": 0.3, "profitMargins": 0.2}
    score, checks = quality(f, Q)
    assert score is None
    assert checks[0]["ok"] is True


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "Infinity", "n/a", ""])
def test_unusable_values_count_as_missing(bad):
    score, checks = quality({**GOOD, "returnOnEquity": bad}, Q)
    assert checks[0]["ok"] is None and checks[0]["value"] is None
    assert score == 100  # the five remaining checks all pass


def test_empty_fundamentals_give_no_score():
    assert quality({}, Q)[0] is None


def test_labels_follow_settings():
    labels = [c.label for c in build_checks(QualitySettings(roe_min=0.15, debt_to_equity_max=100, market_cap_min=5e9))]
    assert labels[0] == "Return on equity >= 15%"
    assert labels[2] == "Debt/equity <= 100%"
    assert labels[5] == "Market cap >= 5B USD"


def test_default_labels_match_dashboard_text():
    assert [c.label for c in build_checks(Q)] == [
        "Return on equity >= 12%", "Net margin >= 8%", "Debt/equity <= 150%",
        "Free cash flow positive", "Revenue growth positive", "Market cap >= 20B USD"]


def test_changed_settings_change_the_result():
    strict = QualitySettings(roe_min=0.30)
    assert quality(GOOD, strict)[0] == 83


# ---- market cap is compared in USD ------------------------------------------
FX = {"EUR": 1.1, "SEK": 0.10, "DKK": 0.15}


def cap_ok(mcap, ccy, fx=FX):
    _, checks = quality({**GOOD, "marketCap": mcap, "currency": ccy}, Q, fx)
    return checks[5]


def test_market_cap_is_converted_to_usd():
    assert cap_ok(353e9, "SEK")["ok"] is True          # 353B SEK is about 35B USD
    assert cap_ok(353e9, "SEK")["value"] == pytest.approx(35.3e9)
    assert cap_ok(150e9, "SEK")["ok"] is False         # 150B SEK is about 15B USD: below 20B
    assert cap_ok(19e9, "EUR")["ok"] is True           # 19B EUR is about 20.9B USD


def test_market_cap_without_a_known_currency_or_rate_has_no_data():
    assert cap_ok(5e11, "NOK")["ok"] is None            # no NOK rate
    assert cap_ok(5e11, None)["ok"] is None
    assert quality({**GOOD, "marketCap": 5e11}, Q, FX)[1][5]["ok"] is None   # currency key absent


def test_market_cap_is_taken_as_usd_when_no_rates_are_given():
    assert quality({**GOOD, "marketCap": 3e10}, Q)[1][5]["ok"] is True


def test_usd_stocks_need_no_rate():
    assert cap_ok(3e10, "USD", {})["ok"] is True


# ---- sector adjustments ------------------------------------------------------
BANK = {**GOOD, "debtToEquity": 900, "freeCashflow": -5e9}


def test_financials_skip_leverage_and_free_cash_flow():
    score, checks = quality(BANK, Q, sector="Financials")
    by_key = {c["key"]: c for c in checks}
    assert by_key["debtToEquity"]["ok"] is None and by_key["debtToEquity"]["na"] is True
    assert by_key["freeCashflow"]["ok"] is None and by_key["freeCashflow"]["na"] is True
    assert score == 100  # the four remaining checks pass


def test_same_numbers_fail_outside_financials():
    score, _ = quality(BANK, Q, sector="Industrials")
    assert score == 67  # 4 of 6 (debt/equity and free cash flow fail)
    assert quality(BANK, Q)[0] == 67  # no sector given: unchanged behaviour


def test_utilities_get_a_relaxed_debt_limit_and_the_label_says_so():
    f = {**GOOD, "debtToEquity": 250}
    score, checks = quality(f, Q, sector="Utilities")
    assert checks[2]["ok"] is True and checks[2]["label"] == "Debt/equity <= 300%"
    assert quality(f, Q, sector="Tech")[1][2]["ok"] is False


def test_relaxed_limit_never_tightens_a_looser_setting():
    loose = QualitySettings(debt_to_equity_max=500)
    assert quality({**GOOD, "debtToEquity": 400}, loose, sector="Utilities")[1][2]["ok"] is True


def test_not_applicable_checks_can_leave_too_little_data():
    f = {"returnOnEquity": 0.2, "profitMargins": 0.1, "debtToEquity": 900, "freeCashflow": -1}
    assert quality(f, Q, sector="Financials")[0] is None  # only 2 checks left with data


@pytest.mark.parametrize("spelling", ["financials", " Financials ", "FINANCIALS"])
def test_sector_matching_ignores_case_and_spaces(spelling):
    assert quality(BANK, Q, sector=spelling)[1][2]["na"] is True


def test_real_estate_gets_the_relaxed_debt_limit_like_utilities():
    f = {**GOOD, "debtToEquity": 250}
    assert quality(f, Q, sector="Real Estate")[1][2]["ok"] is True
    assert quality(f, Q, sector="Tech")[1][2]["ok"] is False


# ---- quality_detail (RES-2): evidence behind the score, must-pass rules, distorted fundamentals -------------
NEG_EQUITY = {k: v for k, v in GOOD.items() if k not in ("returnOnEquity", "debtToEquity")}
PROFILES = [GOOD, NEG_EQUITY, {**GOOD, "returnOnEquity": 1.5}, {**GOOD, "profitMargins": -0.05}, {}, BANK,
            {**GOOD, "freeCashflow": -1, "revenueGrowth": -1}]


def test_full_data_is_ok_and_scored_on_six():
    r = quality_detail(GOOD, Q)
    assert (r.score, r.scored, r.applicable, r.passed, r.status) == (100, 6, 6, 6, "ok")
    assert r.must_failed == () and r.must_missing == () and r.distorted_why is None


@pytest.mark.parametrize("fund", PROFILES)
@pytest.mark.parametrize("sector", [None, "Financials", "Utilities"])
def test_quality_keeps_its_return_and_detail_repeats_it(fund, sector):
    r = quality_detail(fund, Q, sector=sector)
    assert quality(fund, Q, sector=sector) == (r.score, r.checks)


def test_negative_equity_profile_keeps_raw_100_but_is_distorted():
    r = quality_detail(NEG_EQUITY, Q)
    assert (r.score, r.scored, r.applicable, r.status) == (100, 4, 6, "distorted")
    assert "both missing" in r.distorted_why


@pytest.mark.parametrize("roe, status", [(1.5, "distorted"), (1.0000001, "distorted"), (1.0, "ok"), (0.99, "ok")])
def test_roe_distorted_boundary_is_strictly_above_100_percent(roe, status):
    assert quality_detail({**GOOD, "returnOnEquity": roe}, Q).status == status


def test_distorted_roe_threshold_is_a_parameter():
    assert quality_detail({**GOOD, "returnOnEquity": 0.6}, Q, distorted_roe_above=0.5).status == "distorted"


def test_only_one_of_roe_and_debt_missing_is_thin_not_distorted():
    r = quality_detail({k: v for k, v in GOOD.items() if k != "returnOnEquity"}, Q)
    assert (r.status, r.scored) == ("thin", 5)
    assert quality_detail({k: v for k, v in GOOD.items() if k != "debtToEquity"}, Q).status == "thin"


def test_financials_without_roe_is_not_distorted_and_counts_applicable():
    r = quality_detail({k: v for k, v in BANK.items() if k != "returnOnEquity"}, Q, sector="Financials")
    assert r.status == "thin" and r.applicable == 4 and r.scored == 3 and r.distorted_why is None
    full = quality_detail(BANK, Q, sector="Financials")
    assert (full.applicable, full.scored, full.status) == (4, 4, "ok")


def test_financials_with_roe_and_debt_both_missing_is_not_distorted():
    # debt/equity does not apply to a bank, so its absence says nothing about equity
    r = quality_detail({k: v for k, v in BANK.items() if k not in ("returnOnEquity", "debtToEquity")}, Q, sector="Financials")
    assert r.status != "distorted"


def test_status_precedence_no_data_over_distorted_over_thin():
    assert quality_detail({"returnOnEquity": 5.0}, Q).status == "no_data"      # distorted ROE, but too little data
    assert quality_detail({}, Q).score is None
    assert quality_detail({**NEG_EQUITY, "marketCap": None}, Q).status == "distorted"   # 3 scored, distorted beats thin


def test_three_checks_with_data_is_thin_two_is_no_data():
    r = quality_detail({**GOOD, "debtToEquity": None, "freeCashflow": None, "revenueGrowth": None}, Q)
    assert (r.scored, r.status) == (3, "thin") and r.score == 100
    r2 = quality_detail({"profitMargins": 0.2, "freeCashflow": 1}, Q)
    assert (r2.score, r2.status) == (None, "no_data")


def test_intc_like_loss_maker_scores_80_but_fails_must_pass():
    r = quality_detail({**GOOD, "profitMargins": -0.05}, Q)
    assert r.score == 83 and r.status == "ok" and r.must_failed == ("net_margin_positive",)
    f = {**GOOD, "profitMargins": -0.05, "returnOnEquity": 0.01}
    assert quality_detail(f, Q).score == 67


@pytest.mark.parametrize("margin, must_ok, scored_ok", [(0.0, False, False), (0.01, True, False), (0.08, True, True), (-1e-9, False, False)])
def test_net_margin_must_pass_boundary(margin, must_ok, scored_ok):
    r = quality_detail({**GOOD, "profitMargins": margin}, Q)
    assert (r.must_failed == ()) is must_ok
    assert r.checks[1]["ok"] is scored_ok


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "n/a"])
def test_missing_margin_is_listed_not_failed(bad):
    r = quality_detail({**GOOD, "profitMargins": bad}, Q)
    assert r.must_failed == () and r.must_missing == ("net_margin_positive",)


def test_empty_must_pass_reports_nothing():
    r = quality_detail({**GOOD, "profitMargins": -0.5}, Q, must_pass=())
    assert r.must_failed == () and r.must_missing == ()
    assert quality_detail({**GOOD, "profitMargins": None}, Q, must_pass=()).must_missing == ()


def test_unknown_must_pass_rule_raises():
    with pytest.raises(ValueError, match="unknown must_pass"):
        quality_detail(GOOD, Q, must_pass=("net_margin_positve",))


def test_fcf_rule_exists_but_is_off_by_default():
    f = {**GOOD, "freeCashflow": -1}
    assert quality_detail(f, Q).must_failed == ()
    assert quality_detail(f, Q, must_pass=("fcf_positive",)).must_failed == ("fcf_positive",)


def test_negative_equity_cannot_be_labelled_quality_but_keeps_its_score():
    from dipdash.config import Settings
    from dipdash.screen import NO_FUNDAMENTALS, QUALITY_DIP, setup_label
    r = quality_detail(NEG_EQUITY, Q)
    assert setup_label(True, False, r.score, Settings(), q_ok=not r.must_failed, distorted=r.status == "distorted") == NO_FUNDAMENTALS
    assert r.score == 100 and NO_FUNDAMENTALS != QUALITY_DIP


def test_backtest_v3_input_is_unchanged_by_the_new_rules():
    """V3_quality_indicative reads only the stored score; labels may change, the V3 event flags may not."""
    from dataclasses import replace as rep
    from dipdash.backtest import add_events, build_days
    from dipdash.config import Settings, Stock
    from synth import slide, geometric
    S = Settings()
    s = rep(S, backtest=rep(S.backtest, start_date="2025-01-01", horizons=(5,)))
    uni = [Stock(t, t, "US") for t in ("A", "B", "C")]
    prices = {"A": slide(), "B": slide(daily=-0.03), "C": geometric(260, 0.0005)}
    ix = geometric(260, 0.0003)
    funds = {"A": GOOD, "B": NEG_EQUITY, "C": {**GOOD, "profitMargins": -0.05}}
    old = {t: quality(f, s.quality)[0] for t, f in funds.items()}
    new = {t: quality_detail(f, s.quality).score for t, f in funds.items()}
    assert old == new == {"A": 100, "B": 100, "C": 83}
    d_old = add_events(build_days(prices, uni, {"US": ix, "EU": ix}, s, old), s)
    d_new = add_events(build_days(prices, uni, {"US": ix, "EU": ix}, s, new), s)
    assert d_old.equals(d_new) and d_old["ev_V3_quality_indicative"].sum() > 0
    # the labels DO differ: that is the point of the new rule, and it is invisible to the backtest
    labels = {t: quality_detail(f, s.quality) for t, f in funds.items()}
    assert labels["B"].status == "distorted" and labels["C"].must_failed
