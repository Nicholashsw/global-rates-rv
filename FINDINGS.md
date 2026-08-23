# Global Rates RV — Findings (Phase 0 + MVP + Sub-period Analysis)

## Summary of the arc

1. **Full sample (2010–2026):** 0 of 18 candidates cointegrated. No relationships.
2. **Sub-period (4 policy regimes):** 11 of 144 pass the screen, 6 survive FDR.
   **Cointegration does exist within policy regimes.** Hypothesis confirmed.
3. **But it does not survive out of regime.** Fitting in one regime and trading the
   next gives a mean Sharpe of **−0.27**, positive in only **5 of 12** tests.

> **Rebuilt 2026-08-23 on FRED US yields.** The original run used a Bloomberg `USGG*`
> export for the US leg, which is not redistributable and has been removed from the
> repository. The US curve is now FRED `DGS2/5/10/30`. The aligned panel went from
> 3,829 to 3,762 rows, and the headline numbers moved: raw regime passes 7 → 11, FDR
> survivors 3 → 6, out-of-regime mean Sharpe −0.32 → −0.27, positive 2 of 12 → 5 of 12,
> Canada in survivors 6 of 7 → 10 of 11, FX contamination R² max 0.0020 → 0.0016. Every
> conclusion below is unchanged. (The pre-rebuild text also stated "4 survive FDR" in
> prose while its own tables said 3; the tables were right.)

The conclusion is not "there is alpha in regime-conditional cointegration." It is
that within-regime cointegration is **descriptive of the past, not predictive**.

---

## Data (all free, all real)

3,762 aligned daily observations, 2010-01-04 → 2026-06-30, 16 series, no gaps.

| Market | Source | Tenors |
|---|---|---|
| US | FRED constant maturity (`DGS2/5/10/30`) | 2Y 5Y 10Y 30Y |
| Germany | Bundesbank BBSIS (daily, Svensson) | 2Y 5Y 10Y 30Y |
| Japan | Japan MoF daily JGB curve | 2Y 5Y 10Y 30Y |
| **Canada** | **Bank of Canada Valet API** | **2Y 5Y 10Y 30Y** |

Caveats recorded in code: CA 30Y is BoC's generic "LONG" benchmark, not a fixed
30Y constant maturity. JP 2Y has 1,072 zero-change days (yield-curve control).
Negative DE/JP yields are genuine. FRED publishes CMT to two decimal places, coarser
than the other three sources; US 2Y consequently shows 783 zero-change days, and the
raw-pass count below should be read as an upper bound because coarser rounding
flattens residuals.

**UK not added.** The Bank of England endpoint returns HTML rather than CSV for the
series codes tried, and FRED was rate-limited in this environment. Germany/UK
remains an open, worthwhile pair — it needs correct BoE series codes.

**FX is available** and cached: USD/EUR and USD/JPY from the ECB Data Portal, USD/CAD
from the Bank of Canada Valet API, 2009-01-02 → 2026-07-28. FRED was rate-limited in
this environment, so those two endpoints were used instead. Contamination was measured
directly: regressing each survivor's net return on the relevant currency pair gives
**R² of at most 0.0016** (US2s10s/CA2s10s 0.00041, DE5Y/CA5Y 0.00030, JP2s10s/CA2s10s
0.00030, DE10Y/CA10Y 0.00164). The negative result is a rates finding, not a currency
artifact. FX *hedging cost* — forward points — is still not modelled, so no P&L number
here is realistic.

---

## Sub-period screen: the hypothesis was right

Regimes defined *a priori* from monetary-policy history, not from the results:

| Regime | Passes (raw) | Passes (FDR) |
|---|---|---|
| 2010–2014 post-GFC QE | 1 | 1 |
| 2015–2019 divergence/NIRP | 3 | 1 |
| 2020–2021 COVID | 5 | 3 |
| 2022–2026 hiking/normalisation | 2 | 1 |

FDR is applied across the **entire 144-test grid** (36 candidates × 4 periods), not
within each period — correcting per-period would understate the tests performed.

Survivors, with FDR-surviving half-lives in the tradable 8–25 day range rather than
the 81–1,035 days of the full sample:

| Candidate | Regime | β | ADF p | FDR p | Half-life | β CV | FDR pass |
|---|---|---|---|---|---|---|---|
| US2s10s vs CA2s10s | 2022–2026 | 0.73 | 0.0000 | 0.0011 | 10.3 | 0.17 | yes |
| JP2s10s vs CA2s10s | 2020–2021 | 0.06 | 0.0003 | 0.0079 | 8.1 | 0.10 | yes |
| US5Y vs CA5Y | 2020–2021 | 0.97 | 0.0003 | 0.0083 | 10.1 | 0.07 | yes |
| DE5Y vs CA5Y | 2020–2021 | 0.15 | 0.0029 | 0.0379 | 10.5 | 0.27 | yes |
| US2s10s vs CA2s10s | 2010–2014 | 1.12 | 0.0049 | 0.0475 | 25.1 | 0.39 | yes |
| DE5Y vs JP5Y | 2015–2019 | 1.68 | 0.0049 | 0.0475 | 21.5 | 0.43 | yes |
| DE10Y vs CA10Y | 2020–2021 | 0.26 | 0.0131 | 0.1000 | 10.8 | 0.30 | no |
| US2Y vs CA2Y | 2015–2019 | 1.16 | 0.0213 | 0.1278 | 61.2 | 0.63 | no |
| DE5s30s vs CA5s30s | 2022–2026 | 0.76 | 0.0348 | 0.1789 | 18.1 | 0.75 | no |
| US10Y vs CA10Y | 2020–2021 | 0.93 | 0.0397 | 0.1879 | 13.8 | 0.10 | no |
| US5s30s vs CA5s30s | 2015–2019 | 0.74 | 0.0466 | 0.1959 | 38.2 | 0.42 | no |

**Canada appears in 10 of 11 raw survivors and 5 of 6 FDR survivors** — as predicted,
the tighter US/Canada policy linkage produces the relationships the three
most-divergent markets could not.

**Most stable candidate:** US2s10s vs CA2s10s passes in 2 of 4 regimes — both times
surviving FDR — with the tightest β range (0.53) of any repeat performer.

---

## The decisive test: fit one regime, trade the next

Z-score lookback `window=126` (the module default of 252 gives a mean of −0.17 on the
same twelve tests; the sensitivity is discussed below).

| Pair | Fit regime | Test regime | β fit | OOS trades | OOS Sharpe |
|---|---|---|---|---|---|
| US2s10s/CA2s10s | 2010–2014 | 2015–2019 | 1.12 | 25 | −0.81 |
| US2s10s/CA2s10s | 2015–2019 | 2020–2021 | 1.26 | 15 | **+0.02** |
| US2s10s/CA2s10s | 2020–2021 | 2022–2026 | 1.00 | 19 | **+0.53** |
| DE5Y/CA5Y | 2010–2014 | 2015–2019 | 1.28 | 20 | −0.07 |
| DE5Y/CA5Y | 2015–2019 | 2020–2021 | 0.04 | 7 | −2.18 |
| DE5Y/CA5Y | 2020–2021 | 2022–2026 | 0.15 | 18 | −0.11 |
| JP2s10s/CA2s10s | 2010–2014 | 2015–2019 | 0.35 | 21 | **+0.05** |
| JP2s10s/CA2s10s | 2015–2019 | 2020–2021 | 0.20 | 10 | **+0.21** |
| JP2s10s/CA2s10s | 2020–2021 | 2022–2026 | 0.06 | 23 | −0.05 |
| DE10Y/CA10Y | 2010–2014 | 2015–2019 | 1.20 | 21 | −0.46 |
| DE10Y/CA10Y | 2015–2019 | 2020–2021 | 0.43 | 7 | −0.47 |
| DE10Y/CA10Y | 2020–2021 | 2022–2026 | 0.26 | 13 | **+0.08** |

**Mean OOS Sharpe −0.27; positive in 5 of 12** — and the five positives are small
(+0.02 to +0.53) while the losses run to −2.18.

Look at the β column: DE5Y/CA5Y is fit at 1.28, then 0.04, then 0.15. The hedge
ratio is not stable across regimes, so a position sized in one regime is simply the
wrong position in the next. That is the mechanism behind the negative OOS result.

---

## Why in-period backtests also lost money (diagnosed, not hidden)

**9 of the 11 raw-screen survivors had a negative in-period Sharpe** even when traded
inside their own fitting window — the window the relationship was selected on. The two
exceptions are marginal: US2s10s/CA2s10s at +0.25 (9 trades) and US2Y/CA2Y at +0.14
(5 trades). The worst is DE10Y/CA10Y at −1.74.

Diagnosis on US2s10s/CA2s10s (2022–2026), at the default settings:

- 252-day z-score warm-up + 126-day vol warm-up consumes ~36% of a 1,021-day window
- Only **9 trades**, in position **93 of 1,021 days (9%)**
- With 9 trades, Sharpe is noise: one bad trade dominates

Shortening the z-score window raises the trade count and moves the Sharpe around a
lot — for this pair, +0.25 at window 252, +0.37 at 126, +0.59 at 63 (9, 12 and 21
trades respectively). **A Sharpe that swings from 0.25 to 0.59 on the lookback alone is
itself evidence of fragility**, and the out-of-regime test above is the honest verdict.

---

## What is defensible to claim

**Supported:**
- Cross-country government yield spreads were **not** cointegrated over the full
  2010–2026 sample (18/18 rejected).
- Cointegration **does** appear within individual policy regimes (6 of 144 survive
  FDR), with tradable half-lives of 8–25 days.
- Those relationships **do not persist out of regime** (mean OOS Sharpe −0.27, and
  9 of 11 raw survivors lose money even in-period), primarily because the hedge
  ratio β is unstable across regimes.
- Canada is the most-connected market in the set; Japan pairs are the weakest, as
  YCC-era anomalies predict.

**Not supported (do not claim):**
- Any tradable cross-country RV strategy. Nothing here clears out-of-sample.
- Any P&L number as realistic — FX hedging cost is not modelled and costs are a flat
  proxy. FX *contamination* has been measured (R² ≤ 0.0016) and is negligible; FX
  *carry* has not.

---

## Next steps, in priority order

1. **Model FX hedging cost** (forward points). Spot FX is in hand and contamination is
   negligible, but no P&L claim survives review until the hedge carry is priced.
2. **Add UK** (correct BoE series codes) and complete the Germany/UK pair, the one
   remaining high-prior relationship untested.
3. **Time-varying β (Kalman)** — the diagnosis points straight here: β instability
   across regimes is the identified failure mechanism, so a Kalman-filtered hedge
   ratio is the theoretically motivated fix, not a fishing expedition.
4. **Shorter estimation windows** as a pre-registered choice (63–126 day z-score),
   fixed *before* looking at results, to avoid the parameter-sensitivity trap above.
5. Only then: HMM regimes, futures returns, credit.

---

## Code map

`ratslib/` — shared core, verified to reproduce the Treasury results
(`io`, `calendar`, `futures`, `backtest`, `metrics`, `stats`).
`gr_rv/data_mvp.py` — acquisition, caching, coverage report, fault-tolerant markets.
`gr_rv/strategy_mvp.py` — universe, cointegration screen, pairs backtest, FDR, walk-forward.
`gr_rv/subperiod.py` — regime windows, grid screen with global FDR, stability report,
in-period backtests, and `forward_test_survivor` (the fit-one-regime/trade-next test).

Screen validated against synthetic data with known answers: recovers a constructed
cointegrated pair (beta-hat 1.99 vs true 2.00, half-life 16.9d, ADF p<0.0001) and
correctly rejects two independent random walks.
