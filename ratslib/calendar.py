"""Trading-calendar alignment.

The recurring failure mode in this data: index vendors stamp prior values on
non-trading days (New Year, July 4, Christmas), which silently pollutes return
and carry maths. The fix is always the same -- pick one instrument's real
trading calendar as the master and inner-join everything onto it.
"""
import pandas as pd


def master_calendar(*series_or_frames):
    """Intersection of the indices of everything passed in."""
    idx = None
    for s in series_or_frames:
        if s is None or len(s) == 0:
            continue
        i = s.index
        idx = i if idx is None else idx.intersection(i)
    return idx if idx is not None else pd.DatetimeIndex([])


def align(frames: dict, calendar, how="inner", min_coverage=0.0):
    """Reindex a dict of Series/DataFrames onto `calendar`.

    how='inner'  -> drop rows not on the calendar (kills phantom holiday rows)
    min_coverage -> drop columns whose non-NA share is below this threshold
    """
    out = {}
    for k, v in frames.items():
        if v is None:
            continue
        w = v.reindex(calendar)
        if min_coverage > 0:
            cov = w.notna().mean()
            cov = cov.mean() if hasattr(cov, "mean") and not isinstance(cov, float) else cov
            if cov < min_coverage:
                continue
        out[k] = w
    return out


def panel(series_map: dict, calendar=None, dropna_how="all"):
    """Build a DataFrame from {name: Series}, optionally on a master calendar."""
    df = pd.DataFrame({k: pd.Series(v) for k, v in series_map.items() if v is not None})
    df = df.sort_index()
    if calendar is not None:
        df = df.reindex(calendar)
    return df.dropna(how=dropna_how)


def common_span(df, min_obs=250):
    """Trim to the span where all columns have data (for fair cross-market work)."""
    d = df.dropna()
    if len(d) < min_obs:
        return df.dropna(how="all")
    return df.loc[d.index.min():d.index.max()]
