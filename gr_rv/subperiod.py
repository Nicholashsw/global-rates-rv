"""
Global Rates RV -- sub-period (policy-regime) cointegration analysis.

Motivation: the full-sample screen rejected all candidates. But 2010-2026 spans
several structurally different monetary-policy regimes, and a relationship can be
stable *within* a regime while being destroyed by the transitions between them.
Testing regime-by-regime is the natural next question.

The danger: slicing into K periods multiplies the number of tests by K, so the
chance of a spurious "discovery" rises accordingly. Every result here is therefore
FDR-corrected across the ENTIRE grid (all pairs x all periods), not within each
period separately, and the full grid is reported -- passes and failures alike.
"""
import numpy as np
import pandas as pd

from ratslib import metrics, stats
from gr_rv import strategy_mvp as S

# Policy-regime windows, defined by monetary-policy history rather than by
# looking at the results (defining them post hoc would be its own bias).
PERIODS = {
    "2010-2014 post-GFC QE":       ("2010-01-01", "2014-12-31"),
    "2015-2019 divergence/NIRP":   ("2015-01-01", "2019-12-31"),
    "2020-2021 COVID":             ("2020-01-01", "2021-12-31"),
    "2022-2026 hiking/normalis.":  ("2022-01-01", "2026-12-31"),
}

# Everything in this module screens all four markets. strategy_mvp's own default
# is the three-market MVP set, which cannot resolve any Canada pair -- and Canada
# is in most of the survivors, so that default is the wrong one here.
MARKETS = ("US", "DE", "JP", "CA")


def _resolve_universe(universe=None, grid=None):
    """Return the candidate universe to work with.

    Defaults to the four-market universe. When a grid is supplied, every name in
    it must be covered, so a grid built from a different universe fails with a
    readable error instead of a bare KeyError deep inside a loop.
    """
    uni = universe if universe is not None else S.candidate_universe(markets=MARKETS)
    if grid is not None and len(grid):
        missing = sorted(set(grid["name"]) - {c["name"] for c in uni})
        if missing:
            raise ValueError(
                "grid contains candidates absent from the universe: "
                f"{missing[:5]}{'...' if len(missing) > 5 else ''}. "
                "Pass the same `universe=` the grid was screened with.")
    return uni


def subperiod_screen(panel, universe=None, periods=None, min_obs=250,
                     alpha=0.05, **screen_kw):
    """Run the cointegration screen within each policy regime.

    Returns a tidy DataFrame with one row per (candidate, period), FDR-corrected
    across the whole grid using the residual-ADF p-value.
    """
    universe = _resolve_universe(universe)
    periods = periods or PERIODS
    rows = []
    for pname, (a, b) in periods.items():
        sub = panel.loc[(panel.index >= a) & (panel.index <= b)]
        if len(sub) < min_obs:
            continue
        sc = S.screen(sub, universe, **screen_kw)
        if sc.empty:
            continue
        sc = sc.copy()
        sc["period"] = pname
        sc["period_n"] = len(sub)
        rows.append(sc)
    if not rows:
        return pd.DataFrame()
    grid = pd.concat(rows, ignore_index=True)

    # FDR across the WHOLE grid: pairs x periods. Correcting within each period
    # separately would understate the true number of tests performed.
    rej, adj = stats.benjamini_hochberg(grid["adf_p"].values, alpha=alpha)
    grid["adf_p_fdr"] = adj
    grid["adf_signif_fdr"] = rej
    grid["passes_fdr"] = grid["passes"] & grid["adf_signif_fdr"]
    return grid


def stability_report(grid):
    """How consistent is each candidate across regimes?

    A relationship that only appears in one window out of four is far weaker
    evidence than one that survives several, even if the single-window p-value
    looks good.
    """
    if grid.empty:
        return pd.DataFrame()
    g = grid.groupby("name")
    out = pd.DataFrame({
        "periods_tested": g.size(),
        "periods_passed": g["passes"].sum(),
        "periods_passed_fdr": g["passes_fdr"].sum(),
        "median_half_life": g["half_life"].median(),
        "median_beta": g["beta"].median(),
        "beta_range": g["beta"].max() - g["beta"].min(),
        "best_adf_p": g["adf_p"].min(),
    })
    return out.sort_values(["periods_passed_fdr", "periods_passed"],
                           ascending=False)


def backtest_subperiod_survivors(panel, grid, universe=None, top_n=None, **kw):
    """Backtest every (candidate, period) that passed, INSIDE that period only.

    Reports in-sample-to-the-period performance. This is deliberately not
    presented as a tradable result: the period boundaries are known ex post, so
    these numbers are an upper bound, not an expectation.
    """
    if grid.empty:
        return pd.DataFrame()
    universe = _resolve_universe(universe, grid)
    by_name = {c["name"]: c for c in universe}
    winners = grid[grid["passes"]].copy()
    if top_n:
        winners = winners.nsmallest(top_n, "adf_p")
    rows = []
    for _, r in winners.iterrows():
        a, b = PERIODS[r["period"]]
        sub = panel.loc[(panel.index >= a) & (panel.index <= b)]
        c = by_name[r["name"]]
        try:
            res = S.run_candidate(sub, c, r["beta"], **kw)
        except Exception:                            # noqa: BLE001
            continue
        net = res["net"].dropna()
        if len(net) < 60:
            continue
        m = metrics.summary(net, res["turnover"],
                            n_trades=res.attrs.get("n_trades"),
                            avg_hold=res.attrs.get("avg_hold_days"))
        m.update({"name": r["name"], "period": r["period"],
                  "half_life": r["half_life"], "beta": r["beta"],
                  "adf_p": r["adf_p"], "passes_fdr": r["passes_fdr"]})
        rows.append(m)
    df = pd.DataFrame(rows)
    return df.sort_values("sharpe", ascending=False) if not df.empty else df


def forward_test_survivor(panel, cand, fit_period, test_period, **kw):
    """The decisive test: fit beta in one regime, trade it in the NEXT regime.

    If a relationship discovered in period t vanishes in period t+1, it was a
    description of history rather than a strategy.
    """
    fa, fb = PERIODS[fit_period]
    ta, tb = PERIODS[test_period]
    fit = panel.loc[(panel.index >= fa) & (panel.index <= fb)]
    ya = S._series_for(fit, cand["a"], cand["legs_a"])
    yb = S._series_for(fit, cand["b"], cand["legs_b"])
    eg = stats.engle_granger(ya, yb)
    if not eg.get("n") or not np.isfinite(eg.get("beta", np.nan)):
        return None
    test = panel.loc[(panel.index >= ta) & (panel.index <= tb)]
    if len(test) < 120:
        return None
    # include a warm-up tail from the fit period so the z-score is defined
    warm = fit.tail(252)
    combo = pd.concat([warm, test])
    combo = combo[~combo.index.duplicated()]
    res = S.run_candidate(combo, cand, eg["beta"], **kw)
    net = res["net"].reindex(test.index).dropna()
    if len(net) < 60:
        return None
    return {"name": cand["name"], "fit": fit_period, "test": test_period,
            "beta_fit": eg["beta"], "fit_adf_p": eg["adf_p"],
            "fit_half_life": eg["half_life"], "oos_n": len(net),
            "oos_sharpe": metrics.sharpe(net),
            "oos_return": metrics.ann_return(net),
            "oos_max_dd": metrics.max_drawdown(net),
            "oos_trades": res.attrs.get("n_trades")}
