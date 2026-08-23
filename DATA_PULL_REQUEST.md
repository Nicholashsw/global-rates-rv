# Data Pull Request — what I could not reach, and exactly where to get it

## Status after retrying

| Item | Status | Source used |
|---|---|---|
| US 2/5/10/30Y | **DONE** | FRED constant maturity (`DGS2/5/10/30`) |
| Germany 2/5/10/30Y | **DONE** | Bundesbank BBSIS API (daily, 1972–2026) |
| Japan 2/5/10/30Y | **DONE** | Japan MoF daily JGB curve (1974–2026) |
| Canada 2/5/10/30Y | **DONE** | Bank of Canada Valet API (2009–2026) |
| **FX (USD/EUR, USD/JPY, USD/CAD)** | **SOLVED — no longer needed from you** | ECB Data Portal + BoC Valet (2009–2026, cached) |
| **UK gilt yields 2/5/10/30Y** | **BLOCKED — need you** | see below |

FRED is rate-limited from my environment, so I routed around it: ECB and Bank of
Canada gave the FX panel directly. Cross-checked USD/JPY ≈ 163.9 against the
earlier FRED value of 163.71. **FX is done; ignore any earlier request for it.**

---

## The one thing I still need: UK gilt yields

**What:** daily UK government (gilt) benchmark yields, 2Y / 5Y / 10Y / 30Y,
2009-01-01 to present.

**Why it matters:** Germany–UK is the last untested high-prior pair. Two ECB/BoE
economies with tighter policy linkage than the US–Japan pairs that dominate the
current failures. Given Canada appeared in 6 of 7 sub-period survivors precisely
*because* of policy linkage, the UK is the natural next test of the same logic.

**Why I can't get it:** the Bank of England's `fromshowcolumns.asp` endpoint returns
HTML rather than CSV for the series codes I tried (IUDSNPY, IUDMNPY, IUDMNZC,
IUDLNPY), and stooq is JavaScript-gated.

### Easiest options for you, in order

**1. LSEG / Refinitiv (you have this — cleanest route)**
RIC codes for UK benchmark gilts:
- `GB2YT=RR` (2Y), `GB5YT=RR` (5Y), `GB10YT=RR` (10Y), `GB30YT=RR` (30Y)
Pull daily close, 2009-01-01 → today. Export CSV, one file per tenor or one
combined with a Date column.

**2. Bank of England (free, no login) — if you'd rather not use LSEG**
Go to the BoE Database (`bankofengland.co.uk/boeapps/database`), search the gilt
nominal spot-yield series, select 2/5/10/30 year, set the date range, and export CSV.
Alternatively their "Yield curve data" page publishes fitted nominal spot curves as
spreadsheet downloads (`GLC Nominal daily data`), which contain all tenors at once —
that single file would cover everything.

**3. CEIC (you have this)** — search "United Kingdom Government Bond Yield" and
export the 2/5/10/30Y daily series.

### Format I need
Any of these work; I'll adapt:
- One CSV per tenor: `Date,Yield`
- Or one CSV: `Date,2Y,5Y,10Y,30Y`
- Yields in percent (e.g. `4.25`), daily frequency

Name them anything obvious (`UK_yields.csv` is ideal) and upload.

---

## Optional extras, only if convenient while you're in there

These are *nice-to-have*, not blockers. Skip if it's any trouble.

- **UK 2s10s completeness:** if the BoE fitted-curve file is easy, grab it — it
  gives every tenor and removes the need for four separate pulls.
- **Australia (RBA F2 series):** would add a fifth market with a commodity-currency
  linkage to Canada, which is a genuinely interesting pair to test.

## Not needed — please don't spend time on these

- **FX** — solved above.
- **Markit CDS/CDX** — your WRDS has sample-only access; not enough for a real
  backtest, and credit is a later phase anyway.
- **Compustat** — equity fundamentals, irrelevant to this project.
- **Bloomberg international futures** — still the grab-now item *if* you want the
  futures-return version, but the cash-yield MVP needs none of it, and on current
  evidence (nothing survives out-of-sample) I would not spend expiring Bloomberg
  time on it yet.
