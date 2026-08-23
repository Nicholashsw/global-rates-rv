"""
Futures mechanics: continuous back-adjusted series and DV01-neutral hedging.
"""
import numpy as np
import pandas as pd


def continuous(df, price_col="PX_SETTLE", gen_col="FUT_CUR_GEN_TICKER"):
    """Difference back-adjusted continuous series from a front-generic export.

    Roll dates are identified from the generic->contract mapping, and the
    settlement gap on each roll is removed by subtracting the cumulative sum of
    all *future* roll gaps from each historical level. Without this the roll
    jump is booked as a return, which it is not.

    Returns (DataFrame[cont, ret], n_rolls).
    """
    s = df[price_col].copy()
    if gen_col in df.columns:
        gt = df[gen_col].astype(str)
        roll = gt.ne(gt.shift()) & gt.shift().notna()
    else:
        roll = pd.Series(False, index=s.index)
    gaps = pd.Series(np.where(roll, s - s.shift(), 0.0), index=s.index)
    future_gaps = gaps[::-1].cumsum()[::-1].shift(-1).fillna(0.0)
    cont = s - future_gaps
    ret = cont.diff() / cont.shift().abs()
    return pd.DataFrame({"cont": cont, "ret": ret}), int(roll.sum())


def rolling_dv01_beta(fut_ret, cash_yield, window=252):
    """Fallback DV01 proxy: rolling beta of futures return on cash-yield change.
    Use only when a real DV01 series is unavailable."""
    d = pd.concat([pd.Series(fut_ret).rename("fr"),
                   pd.Series(cash_yield).diff().rename("dy")], axis=1).dropna()
    if len(d) < window + 10:
        return pd.Series(dtype=float)
    cov = d["fr"].rolling(window).cov(d["dy"])
    var = d["dy"].rolling(window).var()
    return cov / var


def hedge_ratio(dv01_short, dv01_long, lo=0.1, hi=10.0, lag=1):
    """Contracts of the SHORT-maturity leg per 1 LONG-maturity leg for DV01
    neutrality: n_short = DV01_long / DV01_short. Lagged so only past data is used."""
    r = (pd.Series(dv01_long) / pd.Series(dv01_short)).abs()
    return r.shift(lag).clip(lo, hi)


def dv01_neutral_weights(dv01_map: dict, structure="spread", lag=1):
    """Weights for a DV01-neutral book.

    structure='spread'    : {'long': +1, 'short': -h}
    structure='butterfly' : belly +2, wings -h_each  (2s5s10s style)

    dv01_map keys must be 'long'/'short' or 'belly'/'wing_lo'/'wing_hi'.
    """
    if structure == "spread":
        h = hedge_ratio(dv01_map["short"], dv01_map["long"], lag=lag)
        return pd.DataFrame({"long": 1.0, "short": -h})
    if structure == "butterfly":
        h_lo = hedge_ratio(dv01_map["wing_lo"], dv01_map["belly"], lag=lag)
        h_hi = hedge_ratio(dv01_map["wing_hi"], dv01_map["belly"], lag=lag)
        return pd.DataFrame({"belly": 2.0, "wing_lo": -h_lo, "wing_hi": -h_hi})
    raise ValueError(structure)


def synthetic_bond_return(yield_series, duration_years, dv01_per_100=None):
    """Approximate total return of a constant-maturity bond position from yield
    changes alone: r ~= -D * dy  (dy in decimal).

    This is the cash-yield proxy used before real futures returns are available.
    It omits carry/roll and convexity, so it is a SIGNAL-QUALITY approximation,
    not a P&L claim -- state that plainly in any writeup that uses it.
    """
    dy = pd.Series(yield_series).diff() / 100.0      # yields quoted in percent
    return -duration_years * dy


def duration_proxy(tenor_years):
    """Crude modified duration for a par bond at moderate yields.
    Good enough for DV01-neutral *ratios*; replace with real DV01 when available."""
    t = float(tenor_years)
    return t if t <= 2 else t * (1 - 0.012 * (t - 2))
