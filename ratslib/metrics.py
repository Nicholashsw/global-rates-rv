"""Performance metrics. All take a daily return Series."""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def ann_return(r):
    r = pd.Series(r).dropna()
    return r.mean() * TRADING_DAYS if len(r) else np.nan


def ann_vol(r):
    r = pd.Series(r).dropna()
    return r.std() * np.sqrt(TRADING_DAYS) if len(r) else np.nan


def sharpe(r):
    r = pd.Series(r).dropna()
    if len(r) < 2 or r.std() == 0:
        return np.nan
    return np.sqrt(TRADING_DAYS) * r.mean() / r.std()


def sortino(r):
    """Downside-deviation version of Sharpe (penalises only losses)."""
    r = pd.Series(r).dropna()
    if len(r) < 2:
        return np.nan
    downside = r[r < 0]
    dd = downside.std()
    if dd is None or dd == 0 or np.isnan(dd):
        return np.nan
    return np.sqrt(TRADING_DAYS) * r.mean() / dd


def equity_curve(r):
    return (1 + pd.Series(r).fillna(0)).cumprod()


def max_drawdown(r):
    c = equity_curve(r)
    return (c / c.cummax() - 1).min()


def calmar(r):
    """Annualised return over max drawdown magnitude."""
    mdd = max_drawdown(r)
    if mdd is None or mdd == 0 or np.isnan(mdd):
        return np.nan
    return ann_return(r) / abs(mdd)


def turnover_per_year(turnover, n_obs):
    if n_obs <= 0:
        return np.nan
    return float(pd.Series(turnover).fillna(0).sum()) / (n_obs / TRADING_DAYS)


def hit_rate(r):
    r = pd.Series(r).dropna()
    r = r[r != 0]
    return float((r > 0).mean()) if len(r) else np.nan


def summary(r, turnover=None, n_trades=None, avg_hold=None):
    """One-row summary dict for a strategy's daily net returns."""
    r = pd.Series(r).dropna()
    out = {
        "sharpe": sharpe(r),
        "sortino": sortino(r),
        "calmar": calmar(r),
        "ann_return": ann_return(r),
        "ann_vol": ann_vol(r),
        "max_dd": max_drawdown(r),
        "hit_rate": hit_rate(r),
        "n_obs": len(r),
    }
    if turnover is not None:
        out["turnover_yr"] = turnover_per_year(turnover, len(r))
    if n_trades is not None:
        out["n_trades"] = n_trades
    if avg_hold is not None:
        out["avg_hold_days"] = avg_hold
    return out


def summary_frame(results: dict) -> pd.DataFrame:
    """results: {name: dict-from-summary} -> tidy DataFrame."""
    return pd.DataFrame(results).T
