import pytest

from dipdash.fx import fetch_fx_to_usd, usd_value

R = {"EUR": 1.1, "GBP": 1.3, "SEK": 0.1}


@pytest.mark.parametrize("amount, ccy, expected", [
    (100, "USD", 100), (100, "EUR", 110), (100, "SEK", 10),
    (100, "GBp", 1.3), (100, "GBX", 1.3),          # pence: 100p = 1 GBP
])
def test_usd_value(amount, ccy, expected):
    assert usd_value(amount, ccy, R) == pytest.approx(expected)


@pytest.mark.parametrize("amount, ccy", [(100, "NOK"), (100, None), (100, ""), (None, "EUR"), ("n/a", "EUR"), (float("nan"), "EUR")])
def test_usd_value_is_none_when_anything_is_unusable(amount, ccy):
    assert usd_value(amount, ccy, R) is None


def test_fetch_fx_asks_once_per_currency_and_skips_usd_and_failures():
    asked = []

    def fake(sym):
        asked.append(sym)
        return None if sym.startswith("NOK") else 0.5

    out = fetch_fx_to_usd(["USD", "EUR", "EUR", "NOK", None, "GBp"], fake)
    assert out == {"EUR": 0.5, "GBP": 0.5}
    assert sorted(asked) == ["EURUSD=X", "GBPUSD=X", "NOKUSD=X"]
