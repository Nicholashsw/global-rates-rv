"""
Backtest engines. Both enforce the same discipline:
  * signals use information available at t-1, execution at t
  * volatility scaling to a target, with a warm-up and a leverage cap
  * explicit transaction costs
  * no forward-filling of returns

Two engines:
  run_periodic  -- fixed rebalance (monthly), used for the Treasury curve work
  run_pairs     -- event-driven z-score entry/exit, used for cointegration RV
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def month_end_mask(idx):
    s = pd.Series(idx, index=idx)
    return s.groupby([idx.year, idx.month]).transform("max") == idx


def _vol_scale(raw_ret, target_vol, window=63, max_lev=3.0, min_history=126):
    realized = raw_ret.rolling(window).std() * np.sqrt(TRADING_DAYS)
    scale = (target_vol / realized).clip(upper=max_lev).shift(1)
    scale.iloc[:min_history] = np.nan
    return scale.fillna(0.0)


def run_periodic(signal, ret, cost_per_unit=0.0, target_vol=0.10,
                 rebalance="M", max_lev=3.0, min_history=126):
    """Fixed-schedule rebalance engine.

    signal : DataFrame of pre-scale target weights (columns == ret columns)
    ret    : DataFrame of asset returns
    """
    common = ret.dropna(how="all").index
    signal = signal.reindex(common).ffill()
    ret = ret.reindex(common)
    mask = month_end_mask(common) if rebalance == "M" else pd.Series(True, index=common)
    pos = signal.where(mask).ffill().shift(1)
    raw = (pos * ret).sum(axis=1)
    pos = pos.mul(_vol_scale(raw, target_vol, max_lev=max_lev,
                             min_history=min_history), axis=0)
    gross = (pos * ret).sum(axis=1)
    turnover = pos.diff().abs().sum(axis=1)
    return pd.DataFrame({"gross": gross,
                         "net": gross - turnover * cost_per_unit,
                         "turnover": turnover})


def zscore(series, window=252, clip=4.0, lag=1):
    """Rolling z-score using past data only."""
    s = pd.Series(series)
    z = (s - s.rolling(window).mean()) / s.rolling(window).std()
    return z.clip(-clip, clip).shift(lag)


def pair_positions(z, entry=2.0, exit_=0.5, stop=3.5, max_hold=None):
    """Event-driven state machine on a residual z-score.

    Position is -sign(z) at entry (fade the divergence): z high => residual
    too wide => short the rich leg / long the cheap leg => position -1.

    Returns (position Series in {-1,0,+1}, n_trades, avg_holding_days).
    """
    z = pd.Series(z)
    pos = np.zeros(len(z))
    state, held, trades, holds = 0, 0, 0, []
    zv = z.values
    for i in range(len(zv)):
        v = zv[i]
        if np.isnan(v):
            pos[i] = 0.0
            if state != 0:
                holds.append(held)
            state, held = 0, 0
            continue
        if state == 0:
            if abs(v) > entry:
                state = -1 if v > 0 else 1
                trades += 1
                held = 1
        else:
            held += 1
            hit_exit = abs(v) < exit_
            hit_stop = abs(v) > stop
            hit_time = max_hold is not None and held > max_hold
            if hit_exit or hit_stop or hit_time:
                holds.append(held)
                state, held = 0, 0
        pos[i] = state
    if state != 0:
        holds.append(held)
    return (pd.Series(pos, index=z.index), trades,
            float(np.mean(holds)) if holds else np.nan)


def run_pairs(z, leg_returns, weights, cost_per_unit=0.0, target_vol=0.10,
              entry=2.0, exit_=0.5, stop=3.5, max_hold=None,
              max_lev=3.0, min_history=126):
    """Event-driven pairs engine.

    z            : residual z-score (already lagged)
    leg_returns  : DataFrame of the legs' returns
    weights      : DataFrame of per-leg DV01-neutral weights (same columns),
                   signed for a +1 position; multiplied by the position state
    """
    common = leg_returns.dropna(how="all").index
    z = pd.Series(z).reindex(common)
    w = weights.reindex(common).ffill()
    r = leg_returns.reindex(common)

    state, n_trades, avg_hold = pair_positions(z, entry, exit_, stop, max_hold)
    pos = w.mul(state, axis=0).shift(1)             # decide t-1, execute t
    raw = (pos * r).sum(axis=1)
    pos = pos.mul(_vol_scale(raw, target_vol, max_lev=max_lev,
                             min_history=min_history), axis=0)
    gross = (pos * r).sum(axis=1)
    turnover = pos.diff().abs().sum(axis=1)
    out = pd.DataFrame({"gross": gross,
                        "net": gross - turnover * cost_per_unit,
                        "turnover": turnover,
                        "state": state})
    out.attrs["n_trades"] = n_trades
    out.attrs["avg_hold_days"] = avg_hold
    return out


def walk_forward_splits(index, n_splits=5, min_train=756):
    """Expanding-window train/test splits for out-of-sample validation.

    This is the antidote to choosing a signal direction on the full sample:
    every parameter must be fit on `train` and evaluated only on `test`.
    """
    n = len(index)
    if n < min_train + n_splits:
        return []
    fold = (n - min_train) // n_splits
    if fold <= 0:
        return []
    out = []
    for k in range(n_splits):
        tr_end = min_train + k * fold
        te_end = min(tr_end + fold, n)
        if te_end <= tr_end:
            break
        out.append((index[:tr_end], index[tr_end:te_end]))
    return out
