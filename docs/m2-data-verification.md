# M2 data verification

Generated 2026-11-02 06:29 by `scripts/verify_sources.py` (openbb 5.0.0, yfinance 1.7.0). Window: 2026-08-04 to 2026-11-02. Prices compared are **unadjusted** closes (split-adjusted only): the exchange sources do not provide dividend-adjusted prices, so dividend adjustment itself is not verified.

## US closes: Yahoo vs Nasdaq and Cboe

| Ticker | Second source | Days compared | Max difference | Days > 1% | Last bar (Yahoo) | Last bar (other) |
|---|---|---|---|---|---|---|
| AAPL | nasdaq | 63 | 0.0014% | 0 | 2026-10-30 | 2026-10-30 |
| AAPL | cboe | 62 | 0.0000% | 0 | 2026-10-30 | 2026-10-29 |
| MSFT | nasdaq | 63 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| MSFT | cboe | 62 | 0.0000% | 0 | 2026-10-30 | 2026-10-29 |
| JNJ | nasdaq | 63 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| JNJ | cboe | 62 | 0.0000% | 0 | 2026-10-30 | 2026-10-29 |
| KO | nasdaq | 63 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| KO | cboe | 62 | 0.0000% | 0 | 2026-10-30 | 2026-10-29 |
| JPM | nasdaq | 63 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| JPM | cboe | 62 | 0.0000% | 0 | 2026-10-30 | 2026-10-29 |
| INTC | nasdaq | 63 | 0.0052% | 0 | 2026-10-30 | 2026-10-30 |
| INTC | cboe | 62 | 0.0103% | 0 | 2026-10-30 | 2026-10-29 |

## Nordic closes: Yahoo vs Nasdaq Nordic

| Ticker | Second source | Days compared | Max difference | Days > 1% | Last bar (Yahoo) | Last bar (other) |
|---|---|---|---|---|---|---|
| NOKIA.HE | nasdaq_nordic | 64 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| SAMPO.HE | nasdaq_nordic | 64 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| KNEBV.HE | nasdaq_nordic | 64 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| ERIC-B.ST | nasdaq_nordic | 64 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |
| NOVO-B.CO | nasdaq_nordic | 64 | 0.0000% | 0 | 2026-10-30 | 2026-10-30 |

## Market cap: Yahoo vs Nasdaq Nordic (same close)

| Ticker | Currency | Nasdaq Nordic | Yahoo | Difference |
|---|---|---|---|---|
| NOKIA.HE | EUR | 43.37B | 43.37B | 0.01% |
| SAMPO.HE | EUR | 25.04B | 25.04B | 0.01% |
| KNEBV.HE | EUR | 28.66B | 28.66B | 0.00% |
| ERIC-B.ST | SEK | 353.67B | 353.42B | 0.07% |
| NOVO-B.CO | DKK | 1173.68B | 1173.68B | 0.00% |

## Ratios, Nordic: Yahoo (trailing) vs Nasdaq Nordic (last full year)

Different periods, so only gross disagreement is meaningful. Debt/equity is **not comparable**: Yahoo's is a percentage of total debt including leases; Nasdaq Nordic's is a ratio on its own definition.

| Ticker | ROE Nasdaq | ROE Yahoo | Net margin Nasdaq | Net margin Yahoo | D/E Nasdaq (ratio) | D/E Yahoo (%) |
|---|---|---|---|---|---|---|
| NOKIA.HE | 3.1% (FY2025) | 3.9% | 3.3% | 3.8% | 0.1 | 15.8 |
| SAMPO.HE | 26.4% (FY2025) | 24.1% | 19.4% | 15.7% | 0.3 | 34.7 |
| KNEBV.HE | 34.6% (FY2025) | 37.5% | 8.7% | 8.6% | 0.2 | 24.2 |
| ERIC-B.ST | 27.9% (FY2025) | 18.1% | 12.0% | 8.4% | 0.3 | 40.7 |
| NOVO-B.CO | 60.7% (FY2025) | 59.8% | 33.1% | 35.3% | 0.6 | 63.3 |

## Ratios, US: Yahoo (trailing) vs Nasdaq (last full year)

| Ticker | ROE Nasdaq | ROE Yahoo | Net margin Nasdaq | Net margin Yahoo |
|---|---|---|---|---|
| AAPL | 151.9% (FY2025) | 148.8% | 26.9% | 27.6% |
| MSFT | 30.2% (FY2026) | 34.2% | 40.3% | 41.2% |
| JNJ | 32.9% (FY2025) | 20.0% | 28.5% | 16.2% |
| KO | 40.7% (FY2025) | 40.6% | 27.3% | 28.7% |
| JPM | 15.7% (FY2025) | 18.0% | 33.9% | 34.6% |

## Continental Europe: NOT independently verified

No source reachable from the build container covers these lines (OpenBB's default bundle has none; Stooq is blocked by the network policy). Only the internal checks ran.

| Ticker | Bars (1y) | Last bar | Largest 1-day move | Validation findings |
|---|---|---|---|---|
| ASML.AS | 256 | 2026-10-30 | 8.9% | none |
| SAP.DE | 254 | 2026-10-30 | 16.1% | none |
| NESN.SW | 251 | 2026-10-30 | 8.0% | none |
| MC.PA | 256 | 2026-10-30 | 7.9% | none |
| AIR.PA | 256 | 2026-10-30 | 7.8% | none |
| ROG.SW | no data |  |  | Yahoo returned nothing |
| RO.SW | 251 | 2026-10-30 | 6.2% | none |
