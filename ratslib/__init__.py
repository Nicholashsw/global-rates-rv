"""
ratslib -- shared research core for the rates projects.

Extracted from the Treasury Futures Curve project so that both it and the
Global Rates Relative-Value project use one tested implementation of:

  io          Bloomberg CSV loaders (quirk-handling) + free-source fetchers
  calendar    trading-calendar alignment
  futures     continuous back-adjusted series, DV01, hedge ratios
  backtest    vol-scaled, cost-aware, leakage-free engines
  metrics     Sharpe / Sortino / Calmar / drawdown / turnover
  stats       HAC Diebold-Mariano, ADF/KPSS wrappers, FDR control

Nothing here is strategy-specific.
"""
from . import io, calendar, futures, backtest, metrics, stats  # noqa: F401

__all__ = ["io", "calendar", "futures", "backtest", "metrics", "stats"]
__version__ = "0.1.0"
