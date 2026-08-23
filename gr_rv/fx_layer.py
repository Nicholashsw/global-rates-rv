"""
FX treatment for cross-country rates trades.

Why this exists: a US-vs-Germany bond spread trade earns (a) the rates spread you
intended and (b) the EUR/USD move you did not. Without separating them you can
mistake currency P&L for rates alpha. This module makes the choice explicit.

Two conventions, both reported:

  hedged   -- the foreign leg's local-currency return only. This is the honest
              proxy for a currency-hedged book and is the DEFAULT for judging a
              rates strategy. It ignores hedging cost (forward points), which for
              short holding periods is second-order but is NOT zero.

  unhedged -- local return plus the FX return. This is what you actually earn with
              no hedge, and it is usually dominated by currency volatility.

FX series convention (from ratslib.io.fx_panel): foreign currency per 1 USD, so a
RISE means a stronger USD, i.e. a loss on an unhedged long foreign-asset position.
"""
import numpy as np
import pandas as pd

MARKET_FX = {"US": None, "DE": "USDEUR", "JP": "USDJPY", "CA": "USDCAD"}


def fx_return(fx_panel, market):
    """Daily return to a USD-based investor from holding `market`'s currency.

    fx quoted as foreign-per-USD, so foreign-currency appreciation is a FALL in
    the quote; the investor's FX return is therefore -pct_change.
    """
    col = MARKET_FX.get(market)
    if col is None:
        return None                                   # USD base: no FX exposure
    if fx_panel is None or col not in getattr(fx_panel, "columns", []):
        return None
    return -pd.to_numeric(fx_panel[col], errors="coerce").pct_change()


def apply_fx(local_return, fx_panel, market, mode="hedged"):
    """Convert a local-currency leg return into the chosen convention."""
    if mode == "hedged":
        return local_return
    if mode != "unhedged":
        raise ValueError(mode)
    fxr = fx_return(fx_panel, market)
    if fxr is None:
        return local_return
    return local_return.add(fxr.reindex(local_return.index).fillna(0.0),
                            fill_value=0.0)


def fx_contamination(strategy_net, fx_panel, market_a, market_b, window=None):
    """How much of a strategy's P&L is explained by the currency pair?

    Regresses net returns on the relevant FX return. A large R-squared means the
    'rates' result is substantially a currency bet and should not be reported as
    rates alpha.
    """
    ret_a, ret_b = fx_return(fx_panel, market_a), fx_return(fx_panel, market_b)
    parts = [r for r in (ret_a, ret_b) if r is not None]
    if not parts:
        return {"r2": 0.0, "beta": 0.0, "note": "both legs USD-based"}
    x = parts[0] if len(parts) == 1 else (parts[0] - parts[1])
    d = pd.concat([pd.Series(strategy_net).rename("y"),
                   x.rename("x")], axis=1).dropna()
    if window:
        d = d.tail(window)
    if len(d) < 60 or d["x"].std() == 0:
        return {"r2": np.nan, "beta": np.nan, "note": "insufficient overlap"}
    beta = np.polyfit(d["x"].values, d["y"].values, 1)[0]
    pred = beta * d["x"]
    ss_res = ((d["y"] - pred - (d["y"] - pred).mean()) ** 2).sum()
    ss_tot = ((d["y"] - d["y"].mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"r2": float(r2), "beta": float(beta), "n": len(d), "note": ""}
