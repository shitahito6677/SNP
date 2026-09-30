"""
Metrics ของ equity curve รายวัน — Sharpe/Sortino ใช้ risk-free จาก ^IRX (T-bill 13 สัปดาห์, % ต่อปี)

rf รายวัน = IRX(วันก่อนหน้า) / 100 / 252  (ใช้ค่าวันก่อนหน้า = รู้ได้ ณ ต้นวัน)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TD = 252


def _f(x):
    if x is None:
        return None
    x = float(x)
    return None if not np.isfinite(x) else x


def drawdown(v: pd.Series) -> pd.Series:
    return v / v.cummax() - 1


def max_dd_info(v: pd.Series) -> dict:
    dd = drawdown(v)
    if dd.empty or dd.min() >= 0:
        return {"max_dd": 0.0, "peak": None, "trough": None, "recovery": None}
    trough = dd.idxmin()
    peak = v.loc[:trough].idxmax()
    rec = v.loc[trough:]
    rec = rec[rec >= v.loc[peak]]
    return {"max_dd": _f(dd.min()), "peak": str(peak.date()), "trough": str(trough.date()),
            "recovery": str(rec.index[0].date()) if len(rec) else None}


def series_metrics(v: pd.Series, rf_daily: pd.Series, bench: pd.Series | None = None) -> dict:
    v = v.dropna()
    if len(v) < 2:
        return {}
    r = v.pct_change().dropna()
    rf = rf_daily.reindex(r.index).fillna(0.0)
    ex = r - rf
    years = (v.index[-1] - v.index[0]).days / 365.25
    total = v.iloc[-1] / v.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else np.nan
    vol = r.std() * np.sqrt(TD)
    sharpe = ex.mean() * TD / (ex.std() * np.sqrt(TD)) if ex.std() > 0 else np.nan
    down = ex[ex < 0]
    dd_dev = np.sqrt((down ** 2).sum() / len(ex)) * np.sqrt(TD) if len(ex) else np.nan
    sortino = ex.mean() * TD / dd_dev if dd_dev and dd_dev > 0 else np.nan
    mdd = max_dd_info(v)
    out = {"start": str(v.index[0].date()), "end": str(v.index[-1].date()), "days": int(len(v)),
           "total_return": _f(total), "cagr": _f(cagr), "volatility": _f(vol), "sharpe": _f(sharpe),
           "sortino": _f(sortino), **mdd,
           "calmar": _f(cagr / abs(mdd["max_dd"])) if mdd["max_dd"] else None}
    if bench is not None:
        b = bench.reindex(v.index).pct_change().dropna()
        j = pd.concat([r, b], axis=1, keys=["s", "b"]).dropna()
        j = j[(j["s"] != 0) | (j["b"] != 0)]
        if len(j) > 20 and j["b"].var() > 0:
            rfj = rf.reindex(j.index).fillna(0)
            xs, xb = j["s"] - rfj, j["b"] - rfj
            beta = np.cov(xs, xb)[0, 1] / xb.var()
            alpha = (xs.mean() - beta * xb.mean()) * TD
            out.update(beta=_f(beta), alpha=_f(alpha))
    return out


def trade_metrics(trades: pd.DataFrame, round_trips: list, equity: pd.DataFrame) -> dict:
    n = int(len(trades))
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    avg_eq = float(equity["strategy"].mean())
    traded = float(trades["notional"].sum()) if n else 0.0
    closed = [rt for rt in round_trips if rt.get("closed")]
    wins = [rt for rt in closed if rt["pnl"] > 0]
    return {
        "n_trades": n,
        "n_round_trips": len(closed),
        "win_rate": _f(len(wins) / len(closed)) if closed else None,
        "avg_holding_days": _f(np.mean([rt["holding_days"] for rt in closed])) if closed else None,
        "turnover_annual": _f(traded / 2 / avg_eq / years) if avg_eq else None,
        "total_cost": _f(trades["cost"].sum()) if n else 0.0,
        "exposure": _f((1 - equity["cash"] / equity["strategy"]).mean()),
        "avg_holdings": _f(equity["n_holdings"].mean()),
    }


def compute(equity: pd.DataFrame, rf_daily: pd.Series, trades: pd.DataFrame, round_trips: list,
            held_out_start: str) -> dict:
    """equity: index=date, columns strategy/spy/ew/cash/n_holdings"""
    out = {"full": {}, "pre_held_out": None, "held_out": None}
    for name in ("strategy", "spy", "ew"):
        out["full"][name] = series_metrics(equity[name], rf_daily, equity["spy"] if name != "spy" else None)
    out["full"]["strategy"].update(trade_metrics(trades, round_trips, equity))
    ho = pd.Timestamp(held_out_start)
    if equity.index[-1] >= ho and equity.index[0] < ho:
        pre, post = equity.loc[:ho - pd.Timedelta(days=1)], equity.loc[equity.loc[:ho - pd.Timedelta(days=1)].index[-1]:]
        out["pre_held_out"] = {n: series_metrics(pre[n], rf_daily, pre["spy"] if n != "spy" else None) for n in ("strategy", "spy", "ew")}
        out["held_out"] = {n: series_metrics(post[n], rf_daily, post["spy"] if n != "spy" else None) for n in ("strategy", "spy", "ew")}
    m = equity["strategy"].resample("ME").last()
    first = equity["strategy"].iloc[0]
    mr = m.pct_change()
    mr.iloc[0] = m.iloc[0] / first - 1
    out["monthly_returns"] = {str(k.date())[:7]: _f(v) for k, v in mr.items()}
    return out
