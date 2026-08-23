"""Figures for the Global Rates RV negative result.

Regenerates the four figures in ``results/`` from the committed cache, so the
figures and the numbers in README.md / FINDINGS.md always come from one run.

Usage:
    python scripts/make_figures.py

``GRRV_CACHE`` defaults to the committed cache in ``gr_rv/data``; set it to point
somewhere else. Output goes to ``results/`` unless ``GRRV_FIGS`` says otherwise.
"""
import os
import sys
import warnings

warnings.simplefilter("ignore")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.environ.setdefault("GRRV_CACHE", os.path.join(REPO_ROOT, "gr_rv", "data"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from gr_rv import data_mvp as D, strategy_mvp as S, subperiod as SP

plt.rcParams.update({"figure.dpi": 200, "savefig.dpi": 200, "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": .25, "grid.linewidth": .6,
                     "axes.titlesize": 13, "axes.titleweight": "bold",
                     "legend.frameon": False, "figure.autolayout": True})
RED, GRN, BLU, ORG, GRY = "#c0392b", "#1e8449", "#1f5f8b", "#d97706", "#8a8a99"

OUT = os.environ.get("GRRV_FIGS", os.path.join(REPO_ROOT, "results"))
os.makedirs(OUT, exist_ok=True)

# z-score lookback for the forward test; matches the figures to FINDINGS.md
FWD_WINDOW = 126
PAIRS = ["US2s10s_vs_CA2s10s", "DE5Y_vs_CA5Y", "JP2s10s_vs_CA2s10s", "DE10Y_vs_CA10Y"]
BETA_PAIRS = ["US2s10s_vs_CA2s10s", "DE5Y_vs_CA5Y", "DE10Y_vs_CA10Y"]


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", name)


def main():
    bundle = D.load_all(start="2010-01-01")
    panel = bundle["yields"]
    uni = S.candidate_universe(markets=("US", "DE", "JP", "CA"))
    grid = SP.subperiod_screen(panel, uni)
    by = {c["name"]: c for c in uni}

    full = S.screen(panel, S.candidate_universe())
    n_full_pass, n_full = int(full["passes"].sum()), len(full)

    # --- FIG 1: the four 10Y curves ---------------------------------------
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for c, col in zip(["US_10Y", "DE_10Y", "JP_10Y", "CA_10Y"], [BLU, RED, GRN, ORG]):
        ax.plot(panel.index, panel[c], lw=1.4, color=col, label=c.replace("_", " "))
    ax.axhline(0, color=GRY, lw=.8, ls=":")
    ax.set_title("10-year government yields, 2010–2026")
    ax.set_ylabel("Yield (%)")
    ax.legend(ncol=4, loc="upper left")
    ax.text(.015, .05,
            "Divergent QE, negative rates and YCC break any\n"
            "stable long-run relationship across the full sample.",
            transform=ax.transAxes, fontsize=9, color=GRY, va="bottom")
    save(fig, "grrv_fig1_yields.png")

    # --- FIG 2: screen outcome, full sample vs by regime -------------------
    per = grid.groupby("period")[["passes", "passes_fdr"]].sum()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x, w = np.arange(len(per)), .38
    ax.bar(x - w / 2, per["passes"], w, color=BLU, label="Pass screen")
    ax.bar(x + w / 2, per["passes_fdr"], w, color=GRN, label="Survive FDR")
    ax.set_xticks(x)
    ax.set_xticklabels([p.split()[0] for p in per.index])
    ax.set_ylabel(f"Candidates (of {len(uni)})")
    ax.set_title("Cointegration exists within policy regimes — but not across the full sample")
    ax.legend()
    ax.text(.015, .88,
            f"Full sample 2010–2026:  {n_full_pass} of {n_full} cointegrated",
            transform=ax.transAxes, fontsize=10, color=RED, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    save(fig, "grrv_fig2_regime_screen.png")

    # --- FIG 3: fit one regime, trade the next ----------------------------
    seq = list(SP.PERIODS)
    rows = []
    for nm in PAIRS:
        for i in range(len(seq) - 1):
            r = SP.forward_test_survivor(panel, by[nm], seq[i], seq[i + 1],
                                         window=FWD_WINDOW)
            if r:
                rows.append(r)
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    lbl = [f"{r['name'].replace('_vs_', '/')}\n{r['test'].split()[0]}"
           for _, r in df.iterrows()]
    cols = [GRN if v > 0 else RED for v in df["oos_sharpe"]]
    ax.bar(range(len(df)), df["oos_sharpe"], color=cols)
    ax.axhline(0, color="#1a1a2e", lw=1)
    ax.axhline(df["oos_sharpe"].mean(), color=GRY, ls="--", lw=1.2,
               label=f"mean {df['oos_sharpe'].mean():.2f}")
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(lbl, fontsize=7, rotation=45, ha="right")
    ax.set_ylabel("Out-of-regime Sharpe")
    ax.set_title("Fit the hedge ratio in one policy regime, trade it in the next")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0)
    n_pos = int((df["oos_sharpe"] > 0).sum())
    ax.text(.015, .05,
            f"Positive in only {n_pos} of {len(df)} tests, and never by much.\n"
            "Within-regime cointegration is descriptive, not predictive.",
            transform=ax.transAxes, fontsize=9, color=GRY, va="bottom",
            bbox=dict(facecolor="white", edgecolor="none", alpha=.85, pad=3))
    save(fig, "grrv_fig3_out_of_regime.png")

    # --- FIG 4: beta instability ------------------------------------------
    order = {p: i for i, p in enumerate(SP.PERIODS)}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    betas = {}
    for nm, col in zip(BETA_PAIRS, [BLU, RED, GRN]):
        sub = grid[grid["name"] == nm].copy()
        sub["_o"] = sub["period"].map(order)
        sub = sub.sort_values("_o")
        ax.plot(sub["_o"], sub["beta"], "o-", color=col, lw=1.8, ms=7,
                label=nm.replace("_vs_", "/"))
        betas[nm] = list(zip(sub["period"], sub["beta"]))
    ax.set_xticks(range(len(SP.PERIODS)))
    ax.set_xticklabels([p.split()[0] for p in SP.PERIODS])
    ax.set_ylabel("Cointegrating β (hedge ratio)")
    ax.set_title("The failure mechanism: the hedge ratio is not stable across regimes")
    ax.legend()
    ax.grid(axis="x", alpha=0)
    save(fig, "grrv_fig4_beta_instability.png")

    print(f"\nfull sample: {n_full_pass} of {n_full} cointegrated")
    print(f"regime grid: {len(grid)} tests, raw passes {int(grid['passes'].sum())}, "
          f"FDR {int(grid['passes_fdr'].sum())}")
    print("per regime (raw/FDR): " + ", ".join(
        f"{p.split()[0]} {int(r.passes)}/{int(r.passes_fdr)}" for p, r in per.iterrows()))
    print(f"out-of-regime: mean {df['oos_sharpe'].mean():.4f}, positive {n_pos} of {len(df)}")
    print("\nbeta path by regime:")
    for nm, vals in betas.items():
        print(f"  {nm.replace('_vs_', '/'):22s} " +
              "  ".join(f"{p.split()[0]}={v:.4f}" for p, v in vals))


if __name__ == "__main__":
    main()
