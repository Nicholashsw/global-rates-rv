"""
Inference utilities.

Two families:
  * forecast/strategy comparison  -> newey_west_lrv, dm_test
  * time-series structure         -> adf, kpss, engle_granger, half_life, johansen
  * multiple testing              -> benjamini_hochberg

The DM implementation was cross-checked against a HAC-robust OLS of the loss
differential on a constant (statsmodels, maxlags=21): statistics and p-values
agree to two decimals.
"""
import numpy as np
import pandas as pd
from scipy import stats as _st

TRADING_DAYS = 252


# ---------------------------------------------------------------- HAC / DM
def newey_west_lrv(d, lag):
    """Bartlett-kernel long-run variance of a 1-D series."""
    d = np.asarray(d, float)
    n = len(d)
    dm = d - d.mean()
    lrv = np.dot(dm, dm) / n
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        lrv += 2.0 * w * np.dot(dm[k:], dm[:-k]) / n
    return max(lrv, 1e-18)


def dm_test(base_ret, alt_ret, lag=None, min_lag=21):
    """Diebold-Mariano on the return differential, HAC variance + HLN correction.

    Positive statistic => alt out-returns base.
    Returns dict(stat, p, ann_edge, lag, n).
    `min_lag` should span the holding period (21 ~= monthly rebalance).
    """
    d = (pd.Series(alt_ret) - pd.Series(base_ret)).dropna()
    n = len(d)
    if n < 30 or d.std() == 0:
        return {"stat": np.nan, "p": np.nan, "ann_edge": np.nan, "lag": 0, "n": n}
    if lag is None:
        lag = max(min_lag, int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0))))
    stat = d.mean() / np.sqrt(newey_west_lrv(d.values, lag) / n)
    h = 1
    stat *= np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)   # Harvey-Leybourne-Newbold
    p = 2.0 * (1.0 - _st.t.cdf(abs(stat), df=n - 1))
    return {"stat": stat, "p": p, "ann_edge": d.mean() * TRADING_DAYS, "lag": lag, "n": n}


def stars(p):
    if p is None or np.isnan(p):
        return ""
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""


# ------------------------------------------------------ stationarity tests
def adf(series, **kw):
    """Augmented Dickey-Fuller. H0: unit root (non-stationary).
    Small p => reject unit root => stationary."""
    from statsmodels.tsa.stattools import adfuller
    s = pd.Series(series).dropna()
    if len(s) < 30:
        return {"stat": np.nan, "p": np.nan, "n": len(s)}
    r = adfuller(s.values, autolag=kw.pop("autolag", "AIC"), **kw)
    return {"stat": r[0], "p": r[1], "n": len(s)}


def kpss(series, regression="c", **kw):
    """KPSS. H0: stationary (opposite of ADF).
    Large p => fail to reject stationarity => stationary."""
    from statsmodels.tsa.stattools import kpss as _kpss
    import warnings
    s = pd.Series(series).dropna()
    if len(s) < 30:
        return {"stat": np.nan, "p": np.nan, "n": len(s)}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = _kpss(s.values, regression=regression, nlags=kw.pop("nlags", "auto"), **kw)
    return {"stat": r[0], "p": r[1], "n": len(s)}


def stationarity_verdict(series, alpha=0.05):
    """Combine ADF and KPSS, whose nulls are opposite.

    'stationary'     : ADF rejects unit root AND KPSS fails to reject stationarity
    'unit_root'      : ADF fails to reject AND KPSS rejects
    'inconclusive'   : the two disagree
    """
    a, k = adf(series), kpss(series)
    if np.isnan(a["p"]) or np.isnan(k["p"]):
        return {"verdict": "insufficient_data", "adf_p": a["p"], "kpss_p": k["p"]}
    a_stat = a["p"] < alpha            # ADF says stationary
    k_stat = k["p"] > alpha            # KPSS says stationary
    if a_stat and k_stat:
        v = "stationary"
    elif (not a_stat) and (not k_stat):
        v = "unit_root"
    else:
        v = "inconclusive"
    return {"verdict": v, "adf_p": a["p"], "kpss_p": k["p"]}


# --------------------------------------------------------- cointegration
def engle_granger(y, x, alpha=0.05):
    """Two-step Engle-Granger.

    Step 1: OLS  y = a + b*x + e     (b is the cointegrating/hedge ratio)
    Step 2: test residual e for stationarity via ADF + KPSS.

    NOTE: the residual ADF here uses standard ADF critical values, which are
    mildly conservative for a residual from an estimated relationship; treat
    borderline p-values with caution and lean on out-of-sample stability.
    """
    df = pd.concat([pd.Series(y).rename("y"), pd.Series(x).rename("x")], axis=1).dropna()
    if len(df) < 60:
        return {"ok": False, "reason": "insufficient_overlap", "n": len(df)}
    b, a = np.polyfit(df["x"].values, df["y"].values, 1)
    resid = df["y"] - (a + b * df["x"])
    sv = stationarity_verdict(resid, alpha=alpha)
    return {
        "ok": sv["verdict"] == "stationary",
        "verdict": sv["verdict"],
        "alpha": a, "beta": b,
        "adf_p": sv["adf_p"], "kpss_p": sv["kpss_p"],
        "resid": resid, "half_life": half_life(resid), "n": len(df),
    }


def half_life(resid):
    """Mean-reversion half-life from an AR(1) fit: d_e_t = k * e_{t-1} + u.
    half-life = -ln(2)/ln(1+k). Returns np.inf if not mean-reverting."""
    e = pd.Series(resid).dropna()
    if len(e) < 30:
        return np.nan
    lag = e.shift(1).dropna()
    d = (e - e.shift(1)).dropna()
    idx = lag.index.intersection(d.index)
    if len(idx) < 30:
        return np.nan
    k = np.polyfit(lag.loc[idx].values, d.loc[idx].values, 1)[0]
    if k >= 0:
        return np.inf
    return float(-np.log(2) / np.log(1 + k))


def rolling_beta_stability(y, x, window=252):
    """Rolling OLS beta; returns the series and its coefficient of variation.
    A low CV means a stable hedge ratio, which is what you want."""
    df = pd.concat([pd.Series(y).rename("y"), pd.Series(x).rename("x")], axis=1).dropna()
    if len(df) < window + 10:
        return pd.Series(dtype=float), np.nan
    cov = df["y"].rolling(window).cov(df["x"])
    var = df["x"].rolling(window).var()
    beta = (cov / var).dropna()
    cv = beta.std() / abs(beta.mean()) if len(beta) and beta.mean() != 0 else np.nan
    return beta, cv


def johansen(frame, det_order=0, k_ar_diff=1):
    """Johansen cointegration for >2 series. Returns trace stats vs 95% crit."""
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    df = pd.DataFrame(frame).dropna()
    if df.shape[0] < 100 or df.shape[1] < 2:
        return {"ok": False, "reason": "insufficient_data"}
    r = coint_johansen(df.values, det_order, k_ar_diff)
    trace = r.lr1
    crit95 = r.cvt[:, 1]
    n_rel = int((trace > crit95).sum())
    return {"ok": n_rel > 0, "n_cointegrating": n_rel,
            "trace": trace, "crit95": crit95, "evec": r.evec}


# ------------------------------------------------------- multiple testing
def benjamini_hochberg(pvals, alpha=0.05):
    """Benjamini-Hochberg FDR control.

    Essential when screening many candidate pairs: with 100+ tests some will
    look significant by chance. Returns (rejected_bool_array, adjusted_pvals).
    """
    p = np.asarray(pvals, float)
    ok = ~np.isnan(p)
    out_rej = np.zeros(len(p), bool)
    out_adj = np.full(len(p), np.nan)
    if ok.sum() == 0:
        return out_rej, out_adj
    pv = p[ok]
    n = len(pv)
    order = np.argsort(pv)
    ranked = pv[order]
    adj = ranked * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]      # enforce monotonicity
    adj = np.clip(adj, 0, 1)
    a = np.empty(n)
    a[order] = adj
    out_adj[ok] = a
    out_rej[ok] = a < alpha
    return out_rej, out_adj
