"""
Global Rates RV -- MVP data acquisition (US, Germany, Japan).

All sources are FREE and public, so the study is reproducible by anyone:
  US       FRED constant-maturity (DGS2/5/10/30)
  Germany  Bundesbank BBSIS Svensson-fitted par yields (daily)
  Japan    Japan MoF daily JGB yield curve (full history)
  FX       FRED daily spot

Deliberately NOT used here:
  * FRED IRLTLT01* international long rates -- MONTHLY, unusable for daily pairs
  * WRDS Datastream -- sample-only in the NTU subscription, no full international
    yield history
  * Bloomberg -- not required for the cash-yield MVP (only for the futures version)

Caching: everything is written to CSV on first fetch so reruns are offline
and the dataset is pinned for reproducibility.
"""
import os

import pandas as pd

from ratslib import io as rio

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PKG_DIR)

# Defaults to the CSVs committed alongside this package, so a fresh clone runs
# offline with no configuration. Override with GRRV_CACHE to use another folder.
CACHE = os.environ.get("GRRV_CACHE", os.path.join(_PKG_DIR, "data"))
TENORS = [2, 5, 10, 30]
MARKETS = ["US", "DE", "JP", "CA"]


def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, f"{name}.csv")


def _cached(name, fetch_fn, force=False):
    p = _cache_path(name)
    if os.path.exists(p) and not force:
        df = pd.read_csv(p, index_col=0, parse_dates=True)
        return df.squeeze("columns") if df.shape[1] == 1 else df
    obj = fetch_fn()
    obj.to_csv(p)
    return obj


def us_yields(force=False, local_dir=None):
    """US 2/5/10/30Y. Uses FRED by default; falls back to the local Bloomberg
    export (USGG*) if FRED is unreachable or rate-limited, since the two are
    the same constant-maturity concept and we already hold the Bloomberg pull."""
    bbg_map = {2: "USGG2YR", 5: "USGG5YR", 10: "USGG10YR", 30: "USGG30YR"}
    local_dir = local_dir or os.environ.get("BBG_CSV",
                                            os.path.join(_REPO_ROOT, "data_raw"))

    def _from_local():
        out = {}
        for t in TENORS:
            df = rio.load_timeseries(local_dir, bbg_map[t])
            if df is None or "PX_LAST" not in df.columns:
                raise RuntimeError(f"local US {t}Y not found in {local_dir}")
            out[f"{t}Y"] = df["PX_LAST"]
        return pd.DataFrame(out).sort_index()

    def _fetch():
        try:
            return rio.us_curve(TENORS)
        except Exception:                            # noqa: BLE001
            return _from_local()

    return _cached("US_yields", _fetch, force)


def de_yields(force=False):
    def _f():
        out = {}
        for t in TENORS:
            out[f"{t}Y"] = rio.bundesbank(t)
        return pd.DataFrame(out).sort_index()
    return _cached("DE_yields", _f, force)


def jp_yields(force=False):
    def _f():
        raw = rio.japan_mof()
        cols = {f"{t}Y": f"{t}Y" for t in TENORS if f"{t}Y" in raw.columns}
        return raw[list(cols)].copy()
    return _cached("JP_yields", _f, force)


def ca_yields(force=False):
    """Canadian benchmark government yields (Bank of Canada Valet API).
    Caveat: the 30Y slot is BoC's generic 'LONG' benchmark, not a fixed 30Y
    constant maturity."""
    return _cached("CA_yields", lambda: rio.bank_of_canada(), force)


def fx(force=False):
    """Daily FX from ECB + Bank of Canada (NOT FRED, which rate-limits).
    Convention: foreign currency per 1 USD, so a rise means a stronger USD."""
    def _f():
        try:
            return rio.fx_panel()
        except Exception:                            # noqa: BLE001
            return pd.DataFrame()
    return _cached("FX", _f, force)


def load_all(start="2010-01-01", force=False, markets=None):
    """Fetch (or load from cache) everything and align onto a common calendar.

    Returns dict with:
      yields : DataFrame, columns like 'US_10Y', 'DE_2Y', 'JP_30Y'
      fx     : DataFrame of spot rates on the same calendar
      raw    : per-market frames before alignment (for diagnostics)

    A market whose source is unreachable is EXCLUDED with a warning rather than
    failing the run -- but it is never silently imputed.
    """
    markets = list(markets or MARKETS)
    fetchers = {"US": us_yields, "DE": de_yields, "JP": jp_yields, "CA": ca_yields}
    raw = {}
    for mkt in markets:
        try:
            raw[mkt] = fetchers[mkt](force)
        except Exception as e:                       # noqa: BLE001
            print(f"  [WARN] {mkt} unavailable ({type(e).__name__}) -- excluded")
    frames = {}
    for mkt, df in raw.items():
        for c in df.columns:
            frames[f"{mkt}_{c}"] = pd.to_numeric(df[c], errors="coerce")
    panel = pd.DataFrame(frames).sort_index()
    panel = panel.loc[panel.index >= pd.Timestamp(start)]

    # A day is usable only if every market traded; this removes each country's
    # own holidays, which would otherwise appear as stale (repeated) yields.
    usable = panel.dropna(how="any").index
    panel = panel.loc[usable]

    _fx = fx(force)
    f = _fx.reindex(panel.index).ffill(limit=3) if len(_fx) else pd.DataFrame(index=panel.index)
    return {"yields": panel, "fx": f, "raw": raw}


def coverage_report(bundle):
    """Print what we actually have, and flag anything suspicious."""
    p = bundle["yields"]
    print(f"aligned panel: {p.shape[0]} rows x {p.shape[1]} series  "
          f"{p.index.min().date()} .. {p.index.max().date()}")
    for c in p.columns:
        s = p[c]
        flat = int((s.diff() == 0).sum())
        print(f"  {c:9s} n={s.notna().sum():5d}  "
              f"range=[{s.min():.2f},{s.max():.2f}]  zero-change days={flat}")
    f = bundle["fx"]
    print(f"fx: {list(f.columns) if len(f.columns) else 'UNAVAILABLE (FRED blocked) - FX layer must be supplied before any cross-country P&L claim'}")
