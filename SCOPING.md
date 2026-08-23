# Global Rates Relative-Value: Data Sourcing and Scope

Scoping map for the **new** project. The Treasury Futures Curve project stays as
its own finished piece; this reuses its infrastructure (loaders, DV01 hedging,
backtest engine, HAC testing) as a shared core. Decisions below reflect your
actual NTU WRDS access and the fact that terminal access is expiring.

Legend: **[free]** public source · **[WRDS]** in your subscription · **[WRDS-sample]**
sample only, not full history · **[BBG]** Bloomberg, grab before access ends.

---

## A. Data to pull, and from where

### A1. Cash government yields — the signal backbone (ESSENTIAL)
Constant-maturity 2Y/5Y/10Y/30Y (plus 3M–1Y short end where used). Free from
central banks; this is what the whole cross-country thesis runs on.

| Market | Best source | Cost | Notes |
|---|---|---|---|
| US | FRED (DGS…) / existing BBG pull | free | already have |
| Germany (Bund/EUR curve) | ECB euro-area yield curve (daily, from 2004) | free | ECB AAA / spot curve is the tradable proxy |
| UK | Bank of England yield-curve data | free | |
| Japan | Japan MoF JGB interest rates | free | heavily shaped by QQE/YCC — caveat, don't over-read pre-2024 |
| Canada | Bank of Canada | free | |
| Australia | RBA (F-series) | free | |
| Singapore | MAS benchmark SGS yields | free | 2Y/5Y/10Y available |

Verdict: **all free.** Better for a reproducible paper than a paywalled feed.
WRDS does **not** cover these beyond Datastream samples, so don't rely on it here.

### A2. Short-rate / policy path (ESSENTIAL for regime + front end)
| Item | Source | Cost |
|---|---|---|
| US SOFR / Fed funds futures, FDTR | existing BBG pull / FRED | free/have |
| Policy rates (all countries) | BIS policy rate database | free |
| OIS curves (SOFR/€STR/SONIA/TONA) | BBG | [BBG] if you want them; free proxies are thin |
| SORA / TONA short-rate futures | SGX | [BBG] only if trading the front end via futures |

### A3. Bond futures — only for the "serious" execution version (DECISION NEEDED NOW)
Cash-yield synthetic returns (Section B) need **none** of this. Actual futures
returns need these, and Bloomberg is the clean source that is **expiring**.

| Contract | Root | Source |
|---|---|---|
| US 2/5/10/Ultra10/Bond/UltraBond | ZT ZF ZN TN ZB UB | already pulled |
| Eurex Schatz/Bobl/Bund/Buxl | DU OE RX UB(eu) | [BBG] grab now |
| Eurex OAT / BTP | | [BBG] grab now |
| JGB futures (JPX) | | [BBG] grab now |

**This is the one grab-now item.** If the futures version matters, pull the
international generics + DV01 (`CONVENTIONAL_CTD_FORWARD_FRSK`) before access ends,
exactly as we did for the US roots. If not, skip and run synthetic.

### A4. FX — ESSENTIAL for any cross-country trade
Cross-country rates P&L is contaminated by currency unless you neutralize it.
| Item | Source | Cost |
|---|---|---|
| Spot USD/EUR, USD/JPY, USD/GBP, USD/CAD, USD/AUD, USD/SGD | FRED / central banks | free |
| FX forward points (for hedge carry) | [BBG] | best from BBG; grab if doing the serious version |

### A5. Credit — the extension where your WRDS actually earns its keep
| Item | Source | Cost | Notes |
|---|---|---|---|
| US corporate bond transactions | **TRACE Enhanced** | [WRDS] full | real trade data — your strongest credit asset |
| Bond reference/characteristics | Mergent FISD | [WRDS-sample] | sample only — limits full-history bond studies |
| Index OAS (IG/HY, by rating) | FRED ICE BofA OAS | free | some series now have restricted windows — verify coverage |
| CDS / CDX levels | Markit | [WRDS-sample] | sample only — not enough for a real CDS backtest |
| Sovereign spreads (BTP–Bund, OAT–Bund, EM–UST) | computed from A1 yields | free | **no new pull** — just differences of yields you already have |

### A6. Regime / macro overlay inputs (for the HMM / filter)
| Feature | Source | Cost |
|---|---|---|
| MOVE, VIX, DXY | have / free | |
| Rates realized vol, 2s10s, 2Y change | derived from A1 | free |
| SPX/SPY | FRED / CRSP [WRDS] | free/have |
| Economic surprise index (Citi CESI) | [BBG] | **data gap** — proprietary; grab from BBG or build a homemade surprise index from release-vs-consensus |
| Central-bank meeting calendar | central bank sites | free |

---

## B. What we ADD — new modules / overlays / extensions
Built on the shared core (loaders, DV01 hedging, backtest engine, HAC test).

**Core new modules (the actual project):**
- **Cointegration engine** — ADF + KPSS on each leg, Engle-Granger residual test,
  Johansen for >2 legs, half-life estimation, rolling-β stability. Not an overlay;
  this is the new heart of the strategy.
- **Pairs execution** — rolling residual z-score, entry `|z|>2`, exit `|z|<0.5`,
  stop `|z|>3.5`, max-hold ~2–3 half-lives, re-estimate on past data only.
  Event-driven, replacing the Treasury project's monthly rebalance.
- **FX layer** — hedge foreign-leg currency or treat FX as an explicit, separately-
  reported source of return/risk. Non-optional for cross-country.
- **Multiple-testing control** — Benjamini-Hochberg FDR across all candidates,
  walk-forward OOS, report every tested pair not just winners. This is the
  make-or-break discipline (see D2).

**Overlays (add after the unfiltered strategy works):**
- **Regime overlay (HMM / Markov-switching)** — extends the existing regime filter;
  use the state to size down / raise thresholds / disable pairs, *not* to predict
  yield direction. Benchmark it against a transparent vol-percentile filter first.
- **Risk model** — decompose exposure into DV01 / curve / country-spread / FX / vol
  buckets; compute VaR, expected shortfall, stress scenarios, marginal contribution
  to risk; drive vol-scaling and portfolio-level drawdown de-risking. This is the
  right home for your "hedging + downside + drawdown" question — as *control*, not
  prediction (risk models don't reliably predict max drawdown; even your own notes
  say so).
- **Kalman time-varying hedge ratio** — replaces static β where the relationship drifts.

**Reporting add-ons (for the writeup, after results exist):**
- **Performance attribution (Brinson / Carino)** — explains *where realized P&L came
  from* (allocation vs selection, linked across periods). Useful for the paper's
  results section; it is not a strategy or a risk model, so keep it minimal and last.
- **Metrics suite** — extend the existing Sharpe/DD to Sortino, Calmar, turnover,
  trade count, average holding period, hit rate.

---

## C. Deliberately EXCLUDED (separate project, or unnecessary)

**Separate project (you may have the data, but it's a different thesis):**
- Equity factor / cross-sectional work (CRSP, Fama-French, IBES) — different project.
- Options / vol-surface strategies (OptionMetrics sample) — this is your **FX options
  VRP** project; the regime series from here feeds it, but don't merge them.
- Full CDS-curve / structural credit modeling — WRDS only has Markit samples; defer
  until you have a real CDS source, or keep credit to TRACE + FRED OAS only.

**Unnecessary for this thesis (skip):**
- ESG, corporate culture, litigation, mutual-fund holdings, audit data — irrelevant.
- Intraday / TAQ — daily frequency is correct for this strategy.
- Citi CESI *if* you're cost-conscious — a homemade surprise index is a fine substitute.
- "Predicting" max drawdown — not a real capability; frame risk as control only.

---

## D. Hard constraints and risks (read before building)

**D1. Bloomberg timing.** The only grab-now items are international bond **futures**
(+ their DV01), FX **forwards**, and Citi **CESI**. Everything else is free or already
pulled. Decide the futures question now; cash-yield synthetic can be built anytime.

**D2. Multiple testing is THE risk.** 7 markets × 4 maturities ≈ 84 same-maturity
pairs + 42 curve spreads = 126 candidates before butterflies. Some *will* look
brilliant by chance. Benjamini-Hochberg + walk-forward + report-all is non-negotiable;
it's the same honesty discipline from the Treasury paper, scaled up. A reviewer's
first question on a 100-pair study is "how did you correct for data snooping."

**D3. FX contamination.** Without FX neutralization you can mistake currency P&L for
rates alpha. Handle it explicitly from day one.

**D4. Japan caveat.** JGB relationships are distorted by QQE / YCC; don't over-read
pre-2024 Japan cointegration.

**D5. Data gaps to accept.** FRED ICE BofA OAS has some restricted windows; Markit
CDS is sample-only in your WRDS; CESI is proprietary. None blocks the MVP.

---

## E. Recommended MVP (prove this before anything else)
- **Markets:** US, Germany, Japan · **Maturities:** 2Y/5Y/10Y/30Y
- **Trades:** same-maturity country spreads + cross-country 2s10s / 5s30s differentials
- **Stats:** Engle-Granger + ADF/KPSS residual test + half-life + rolling-β stability
- **P&L:** DV01-neutral synthetic returns (cash yields), FX handled explicitly
- **Filter:** transparent vol-percentile (HMM comes later)
- **Metrics:** Sharpe, Sortino, Calmar, max DD, turnover, trade count, avg hold
- **Data:** all free (ECB, MoF Japan, FRED, existing US pull) — **zero Bloomberg needed**

Then, in order: actual futures returns/rolls → SG/UK/CA/AU → HMM → Kalman β →
risk model → credit (TRACE + FRED OAS + sovereign spreads) → attribution.
