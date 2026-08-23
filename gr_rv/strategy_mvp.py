"""
Global Rates RV -- MVP strategy engine.

Pipeline:
  1. build the candidate universe (same-maturity cross-country spreads and
     cross-country curve differentials)
  2. screen every candidate for cointegration (Engle-Granger + ADF/KPSS on the
     residual, half-life, rolling-beta stability)
  3. trade the survivors with a z-score entry/exit state machine, DV01-neutral
  4. control for multiple testing (Benjamini-Hochberg) and validate walk-forward

Design decisions worth knowing:
  * Signal is built from yields; P&L is built from DV01-weighted synthetic bond
    returns. A 10bp yield convergence is NOT a 10bp return.
  * The hedge ratio is the cointegrating beta translated into DV01 space, so the
    book is neutral to a parallel shift, not merely 1:1 in yield terms.
  * Every candidate tested is reported, not only the winners.
"""
import itertools

import numpy as np
import pandas as pd

from ratslib import backtest, futures, metrics, stats

TENORS = [2, 5, 10, 30]


# ------------------------------------------------------------- universe
def candidate_universe(markets=("US", "DE", "JP"), tenors=TENORS,
                       include_curve_diffs=True):
    """Return list of dicts describing each candidate spread.

    kind='level' : same-maturity cross-country, e.g. US_10Y vs DE_10Y
    kind='curve' : cross-country slope differential, e.g. US 2s10s vs DE 2s10s
    """
    out = []
    for a, b in itertools.combinations(markets, 2):
        for t in tenors:
            out.append({"name": f"{a}{t}Y_vs_{b}{t}Y", "kind": "level",
                        "a": a, "b": b, "legs_a": [t], "legs_b": [t]})
    if include_curve_diffs:
        for a, b in itertools.combinations(markets, 2):
            for lo, hi in [(2, 10), (5, 30)]:
                out.append({"name": f"{a}{lo}s{hi}s_vs_{b}{lo}s{hi}s",
                            "kind": "curve", "a": a, "b": b,
                            "legs_a": [lo, hi], "legs_b": [lo, hi]})
    return out


def _series_for(panel, mkt, legs):
    """Yield series for one side: a level (one leg) or a slope (two legs)."""
    if len(legs) == 1:
        return panel[f"{mkt}_{legs[0]}Y"]
    lo, hi = legs
    return panel[f"{mkt}_{hi}Y"] - panel[f"{mkt}_{lo}Y"]


# ------------------------------------------------------------- screening
def screen(panel, universe, min_half_life=2, max_half_life=252,
           max_beta_cv=1.0, window=252):
    """Cointegration screen. Returns a tidy DataFrame, one row per candidate.

    A candidate 'passes' when the residual is stationary on BOTH ADF and KPSS,
    the half-life is economically sensible (fast enough to trade, slow enough
    to be real), and the rolling hedge ratio is reasonably stable.
    """
    rows = []
    for c in universe:
        ya = _series_for(panel, c["a"], c["legs_a"])
        yb = _series_for(panel, c["b"], c["legs_b"])
        eg = stats.engle_granger(ya, yb)
        if not eg.get("n"):
            continue
        _, beta_cv = stats.rolling_beta_stability(ya, yb, window=window)
        hl = eg.get("half_life", np.nan)
        passes = (eg["verdict"] == "stationary"
                  and np.isfinite(hl) and min_half_life <= hl <= max_half_life
                  and (np.isnan(beta_cv) or beta_cv <= max_beta_cv))
        rows.append({
            "name": c["name"], "kind": c["kind"],
            "beta": eg["beta"], "adf_p": eg["adf_p"], "kpss_p": eg["kpss_p"],
            "verdict": eg["verdict"], "half_life": hl, "beta_cv": beta_cv,
            "n": eg["n"], "passes": passes,
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------- P&L legs
def leg_returns(panel, c):
    """DV01-weighted synthetic returns for the two sides of a candidate.

    Uses r ~= -D * dy on each cash tenor (see ratslib.futures.synthetic_bond_return).
    For a curve leg (slope), the side is itself a DV01-neutral steepener, so its
    return is the difference of the two tenors' DV01-scaled returns.
    """
    def side(mkt, legs):
        if len(legs) == 1:
            t = legs[0]
            return futures.synthetic_bond_return(panel[f"{mkt}_{t}Y"],
                                                 futures.duration_proxy(t))
        lo, hi = legs
        r_lo = futures.synthetic_bond_return(panel[f"{mkt}_{lo}Y"],
                                             futures.duration_proxy(lo))
        r_hi = futures.synthetic_bond_return(panel[f"{mkt}_{hi}Y"],
                                             futures.duration_proxy(hi))
        return r_hi - r_lo          # already DV01-matched by construction
    return pd.DataFrame({"a": side(c["a"], c["legs_a"]),
                         "b": side(c["b"], c["legs_b"])}).dropna()


# ------------------------------------------------------------- backtest
def run_candidate(panel, c, beta, entry=2.0, exit_=0.5, stop=3.5,
                  window=252, cost=0.00005, target_vol=0.10, max_hold=None):
    """Backtest one candidate with an event-driven z-score state machine."""
    ya = _series_for(panel, c["a"], c["legs_a"])
    yb = _series_for(panel, c["b"], c["legs_b"])
    resid = ya - beta * yb
    z = backtest.zscore(resid, window=window)

    r = leg_returns(panel, c)
    # position +1 means: long side A duration, short beta-scaled side B duration
    w = pd.DataFrame({"a": 1.0, "b": -abs(beta)}, index=r.index)
    res = backtest.run_pairs(z, r, w, cost_per_unit=cost,
                             target_vol=target_vol, entry=entry, exit_=exit_,
                             stop=stop, max_hold=max_hold)
    return res


def screen_and_backtest(panel, universe=None, alpha=0.05, **kw):
    """Full MVP run: screen, backtest survivors, correct for multiple testing.

    Returns (screen_table, results_table, curves_dict).
    Every candidate that was screened appears in screen_table -- including
    failures -- because reporting only the winners is how 126 tests turn into
    a fake discovery.
    """
    universe = universe or candidate_universe()
    sc = screen(panel, universe)
    if sc.empty:
        return sc, pd.DataFrame(), {}

    by_name = {c["name"]: c for c in universe}
    rows, curves = [], {}
    for _, r in sc[sc["passes"]].iterrows():
        c = by_name[r["name"]]
        res = run_candidate(panel, c, r["beta"], **kw)
        net = res["net"]
        m = metrics.summary(net, res["turnover"],
                            n_trades=res.attrs.get("n_trades"),
                            avg_hold=res.attrs.get("avg_hold_days"))
        # is the mean return distinguishable from zero, HAC-corrected?
        d = stats.dm_test(pd.Series(0.0, index=net.index), net)
        m.update({"name": r["name"], "kind": r["kind"],
                  "half_life": r["half_life"], "beta": r["beta"],
                  "t_stat": d["stat"], "p_raw": d["p"]})
        rows.append(m)
        curves[r["name"]] = net

    res_df = pd.DataFrame(rows)
    if not res_df.empty:
        rej, adj = stats.benjamini_hochberg(res_df["p_raw"].values, alpha=alpha)
        res_df["p_fdr"] = adj
        res_df["significant_fdr"] = rej
        res_df = res_df.sort_values("sharpe", ascending=False)
    return sc, res_df, curves


def walk_forward_check(panel, c, n_splits=4, **kw):
    """Refit beta on each training window, evaluate only on the test window.

    This is the antidote to picking a relationship on the full sample: the
    hedge ratio and the z-score normalisation must not see the test data.
    """
    splits = backtest.walk_forward_splits(panel.index, n_splits=n_splits)
    if not splits:
        return pd.DataFrame()
    out = []
    for i, (tr, te) in enumerate(splits, 1):
        ya_tr = _series_for(panel.loc[tr], c["a"], c["legs_a"])
        yb_tr = _series_for(panel.loc[tr], c["b"], c["legs_b"])
        eg = stats.engle_granger(ya_tr, yb_tr)
        if not eg.get("n") or not np.isfinite(eg.get("beta", np.nan)):
            continue
        sub = panel.loc[tr.union(te)]
        res = run_candidate(sub, c, eg["beta"], **kw)
        te_net = res["net"].reindex(te).dropna()
        if len(te_net) < 30:
            continue
        out.append({"fold": i, "train_end": tr.max().date(),
                    "test_n": len(te_net), "beta_train": eg["beta"],
                    "oos_sharpe": metrics.sharpe(te_net),
                    "oos_return": metrics.ann_return(te_net)})
    return pd.DataFrame(out)
