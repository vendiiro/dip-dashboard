import pytest

from dipdash.config import QualitySettings
from dipdash.quality import build_checks, quality

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
