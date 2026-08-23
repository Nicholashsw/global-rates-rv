"""
Data loading.

Part 1: Bloomberg CSV exports (from the VBA puller), with the quirks we found
the hard way -- phantom holiday rows, junk trailing rows, day-first date text
that silently transposes month/day, mixed ticker year formats.

Part 2: free public sources for the multi-country work (FRED, Bundesbank,
Japan MoF). These are deliberately preferred over paywalled feeds: they make
the research reproducible by anyone.
"""
import io as _io
import glob
import os
import ssl
import urllib.request

import numpy as np
import pandas as pd

MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
              "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}

_UA = {"User-Agent": "Mozilla/5.0 (academic research)"}
_CTX = ssl.create_default_context()


# =============================================================== Bloomberg
def find_csv(data_dir, stem):
    """Locate a CSV by security stem, excluding _STATIC / _DV01 side files
    unless the stem explicitly asks for one."""
    hits = glob.glob(os.path.join(data_dir, stem + "*.csv"))
    if "STATIC" not in stem:
        hits = [h for h in hits if "_STATIC" not in os.path.basename(h)]
    if "DV01" not in stem:
        hits = [h for h in hits if "_DV01" not in os.path.basename(h)]
    return hits[0] if hits else None


def load_timeseries(data_dir, stem):
    """Bloomberg BDH export: Date + fields. Trims junk trailing rows."""
    p = find_csv(data_dir, stem)
    if not p:
        return None
    df = pd.read_csv(p)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    for c in df.columns:
        if c != "FUT_CUR_GEN_TICKER":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    price_col = "PX_SETTLE" if "PX_SETTLE" in df.columns else "PX_LAST"
    if price_col in df.columns:
        last = df[price_col].last_valid_index()
        if last is not None:
            df = df.loc[:last]
    return df


def load_static(data_dir, stem, log=None):
    """Futures chain static file. Parses day-first date text and validates the
    delivery month against the ticker's month code -- this catches the locale
    corruption where '1/6/1982' (1 June) is silently read as 6 January."""
    p = find_csv(data_dir, stem + "_STATIC")
    if not p:
        return None
    df = pd.read_csv(p)
    date_cols = [c for c in df.columns if c in
                 ("LAST_TRADEABLE_DT", "FUT_NOTICE_FIRST",
                  "FUT_DLV_DT_FIRST", "FUT_DLV_DT_LAST")]
    for c in date_cols:
        df[c] = pd.to_datetime(df[c].astype(str), dayfirst=True, errors="coerce")

    def _mc(t):
        s = str(t).split()[0]
        for ch in s[::-1]:
            if ch in MONTH_CODE:
                return MONTH_CODE[ch]
        return np.nan

    if "FUT_DLV_DT_FIRST" in df.columns and "CONTRACT" in df.columns:
        code_m = df["CONTRACT"].map(_mc)
        got_m = df["FUT_DLV_DT_FIRST"].dt.month
        bad = int(((code_m == code_m) & (got_m == got_m) & (code_m != got_m)).sum())
        if log:
            log(f"  [{'WARN' if bad else 'ok'}] {stem}: "
                f"{bad} delivery-month/ticker-code mismatches")
    return df


def load_dv01(data_dir, root, calendar=None,
              field="CONVENTIONAL_CTD_FORWARD_FRSK", min_obs=252):
    """Daily forward DV01. Prefers the standalone {root}_DV01.csv produced by the
    single-field puller; falls back to a column inside the futures TS file.

    (The single-field pull exists because bundling this field into a multi-field
    BDH array hangs the request.)
    """
    p = find_csv(data_dir, f"{root}_DV01")
    if p:
        d = pd.read_csv(p)
        d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
        d = d.dropna(subset=["Date"]).set_index("Date").sort_index()
        if field in d.columns:
            s = pd.to_numeric(d[field], errors="coerce")
            if calendar is not None:
                s = s.reindex(calendar)
            if s.notna().sum() > min_obs:
                return s
    ts = load_timeseries(data_dir, root)
    if ts is not None and field in ts.columns:
        s = pd.to_numeric(ts[field], errors="coerce")
        if calendar is not None:
            s = s.reindex(calendar)
        if s.notna().sum() > min_obs:
            return s
    return None


# ============================================================ free sources
_LAST_CALL = {"t": 0.0}
_MIN_INTERVAL = 1.2          # be polite: public endpoints rate-limit bursts


def _get(url, timeout=45, retries=4, backoff=2.5):
    """GET with pacing and exponential backoff.

    Public sources (FRED especially) return 503 when hit with rapid successive
    requests, so we space calls out and retry rather than failing the run.
    """
    import time
    last_err = None
    for attempt in range(retries):
        wait = _MIN_INTERVAL - (time.time() - _LAST_CALL["t"])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                out = r.read().decode("utf-8", "ignore")
            _LAST_CALL["t"] = time.time()
            return out
        except Exception as e:                      # noqa: BLE001
            last_err = e
            _LAST_CALL["t"] = time.time()
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} tries: {url}") from last_err


def fred(series_id, timeout=45):
    """Daily FRED series -> Series. Works for DGS*, DEX* (FX), BAML* (OAS).

    Caution: FRED's international long-rate series (IRLTLT01*) are MONTHLY and
    unsuitable for a daily pairs strategy -- use bundesbank()/japan_mof() instead.
    """
    txt = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
               timeout=timeout)
    df = pd.read_csv(_io.StringIO(txt))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")   # "." -> NaN
    return df.dropna(subset=["date"]).set_index("date")["value"].rename(series_id)


# US Treasury constant-maturity yields (H.15 / CMT) from FRED.
_FRED_CMT = {1: "DGS1", 2: "DGS2", 3: "DGS3", 5: "DGS5",
             7: "DGS7", 10: "DGS10", 20: "DGS20", 30: "DGS30"}


def us_curve(tenors=(2, 5, 10, 30), timeout=45):
    """US constant-maturity yields from FRED as a DataFrame ('2Y', '5Y', ...).

    Free, redistributable public data -- this is the source of record for the
    US leg. Non-trading days come back as NaN and are dropped when the
    cross-country panel is aligned.
    """
    out = {}
    for t in tenors:
        if t not in _FRED_CMT:
            raise ValueError(f"tenor {t} not in {sorted(_FRED_CMT)}")
        out[f"{t}Y"] = fred(_FRED_CMT[t], timeout=timeout)
    return pd.DataFrame(out).sort_index()


# Bundesbank BBSIS Svensson-fitted par yields on listed Federal securities.
_BBK_TENOR = {1: "R01XX", 2: "R02XX", 3: "R03XX", 5: "R05XX",
              7: "R07XX", 10: "R10XX", 20: "R20XX", 30: "R30XX"}


def bundesbank(tenor_years, timeout=45):
    """Daily German government yield for a tenor (1,2,3,5,7,10,20,30)."""
    if tenor_years not in _BBK_TENOR:
        raise ValueError(f"tenor {tenor_years} not in {sorted(_BBK_TENOR)}")
    key = (f"D.I.ZST.ZI.EUR.S1311.B.A604.{_BBK_TENOR[tenor_years]}.R.A.A._Z._Z.A")
    url = (f"https://api.statistiken.bundesbank.de/rest/download/BBSIS/{key}"
           f"?format=csv&lang=en")
    txt = _get(url, timeout=timeout)
    rows = []
    for line in txt.splitlines():
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d = pd.to_datetime(parts[0].strip().strip('"'), errors="coerce",
                           format="%Y-%m-%d")
        if pd.isna(d):
            continue
        v = pd.to_numeric(parts[1].strip().strip('"'), errors="coerce")
        rows.append((d, v))
    s = pd.Series(dict(rows)).sort_index()
    return s.rename(f"DE{tenor_years}Y").dropna()


def japan_mof(timeout=60):
    """Daily JGB yield curve, all tenors, full history -> DataFrame (cols '2Y'...)."""
    url = ("https://www.mof.go.jp/english/policy/jgbs/reference/"
           "interest_rate/historical/jgbcme_all.csv")
    txt = _get(url, timeout=timeout)
    lines = [l for l in txt.splitlines() if l.strip()]
    hdr_i = next(i for i, l in enumerate(lines) if l.split(",")[0].strip() == "Date")
    df = pd.read_csv(_io.StringIO("\n".join(lines[hdr_i:])))
    df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="%Y/%m/%d")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def bank_of_canada(timeout=45, start="2009-01-01"):
    """Daily Canadian benchmark government bond yields -> DataFrame.

    Valet API 'selected bond yields'. Note the long-bond series is a generic
    'LONG' (roughly 30Y) rather than a fixed 30Y constant maturity, so it is
    mapped to '30Y' with that caveat.
    """
    codes = {"2Y": "BD.CDN.2YR.DQ.YLD", "5Y": "BD.CDN.5YR.DQ.YLD",
             "10Y": "BD.CDN.10YR.DQ.YLD", "30Y": "BD.CDN.LONG.DQ.YLD"}
    out = {}
    for label, sid in codes.items():
        txt = _get(f"https://www.bankofcanada.ca/valet/observations/{sid}/csv"
                   f"?start_date={start}", timeout=timeout)
        lines = [l for l in txt.splitlines() if l.strip()]
        hdr = next(i for i, l in enumerate(lines)
                   if l.replace('"', "").startswith("date"))
        df = pd.read_csv(_io.StringIO("\n".join(lines[hdr:])))
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        out[label] = df.dropna(subset=["date"]).set_index("date")["value"]
    return pd.DataFrame(out).sort_index()
    """US constant-maturity yields from FRED -> DataFrame (cols '2Y'...)."""
    out = {}
    for t in tenors:
        out[f"{t}Y"] = fred(f"DGS{t}", timeout=timeout)
    return pd.DataFrame(out).sort_index()


def ecb_fx(currency="USD", denom="EUR", start="2009-01-01", timeout=45):
    """Daily ECB reference rate, quoted as `currency` per `denom` (e.g. USD per EUR).
    FRED-independent, so this still works when FRED rate-limits."""
    url = (f"https://data-api.ecb.europa.eu/service/data/EXR/"
           f"D.{currency}.{denom}.SP00.A?format=csvdata&startPeriod={start}")
    df = pd.read_csv(_io.StringIO(_get(url, timeout=timeout)))
    df = df[["TIME_PERIOD", "OBS_VALUE"]].copy()
    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"], errors="coerce")
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    return df.dropna().set_index("TIME_PERIOD")["OBS_VALUE"].sort_index().rename(
        f"{currency}{denom}")


def boc_fx(series="FXUSDCAD", start="2009-01-01", timeout=45):
    """Daily Bank of Canada FX (FXUSDCAD = CAD per USD)."""
    txt = _get(f"https://www.bankofcanada.ca/valet/observations/{series}/csv"
               f"?start_date={start}", timeout=timeout)
    rows = []
    for line in txt.splitlines():
        p = [x.strip().strip('"') for x in line.split(",")]
        if len(p) < 2:
            continue
        d = pd.to_datetime(p[0], errors="coerce", format="%Y-%m-%d")
        v = pd.to_numeric(p[1], errors="coerce")
        if pd.notna(d) and pd.notna(v):
            rows.append((d, v))
    return pd.Series(dict(rows)).sort_index().rename(series)


def fx_panel(start="2009-01-01", timeout=45):
    """Foreign currency per 1 USD for the MVP markets, from ECB + BoC only.

    A rise in each series = USD stronger.
      USDEUR = 1 / (USD per EUR)
      USDJPY = (JPY per EUR) / (USD per EUR)   [cross via EUR]
      USDCAD = CAD per USD                     [direct]
    """
    usd_eur = ecb_fx("USD", "EUR", start, timeout)
    jpy_eur = ecb_fx("JPY", "EUR", start, timeout)
    out = {"USDEUR": 1.0 / usd_eur, "USDJPY": (jpy_eur / usd_eur).dropna()}
    try:
        out["USDCAD"] = boc_fx("FXUSDCAD", start, timeout)
    except Exception:                                    # noqa: BLE001
        pass
    return pd.DataFrame(out).sort_index()


def fx_spot(pair="USDJPY", timeout=45):
    """Daily FX from FRED. Returned as UNITS OF FOREIGN CURRENCY PER USD so all
    pairs share one convention (DEXUSEU is quoted USD per EUR, so it is inverted)."""
    mapping = {"USDJPY": ("DEXJPUS", False), "USDEUR": ("DEXUSEU", True),
               "USDGBP": ("DEXUSUK", True), "USDCAD": ("DEXCAUS", False),
               "USDAUD": ("DEXUSAL", True), "USDSGD": ("DEXSIUS", False)}
    if pair not in mapping:
        raise ValueError(f"unknown pair {pair}")
    sid, invert = mapping[pair]
    s = fred(sid, timeout=timeout)
    if invert:
        s = 1.0 / s
    return s.rename(pair)
