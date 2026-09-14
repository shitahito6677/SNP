"""
e5_validate.py — exp_04 Phase E5: รัน test ตามที่ pre-register ไว้ใน `PRE_REGISTERED_TEST.md`
เป๊ะๆ ไม่ปรับอะไรเพิ่มเติมหลังเห็นผล

**ย้ำกฎ:** ไฟล์ `PRE_REGISTERED_TEST.md` ต้อง commit ก่อนไฟล์นี้ถูกรันเสมอ (ตรวจสอบ git log ได้)
เกณฑ์/metric/scope ทั้งหมดอ้างอิงจากไฟล์นั้น **ห้ามเปลี่ยนที่นี่**

Input :
    model_c_rulebase/scripts/r5b_validate.py::run_engine_on_all_news()  (reuse ของเดิม, ไม่ก็อป
        logic ใหม่ — `sector_impact_score` ต้องมาจาก engine เดียวกับที่ exp_03 ใช้จริงเป๊ะ)
    model_c_event_clustering/data/e3_cluster_assignments.csv  (E3 — cluster เสถียรเท่านั้น)
    model_c_rulebase/data/r5_rho_table.csv  (สำหรับ triangulation check กับผล R5 เดิม)
Output:
    model_c_event_clustering/data/e5_test_results.csv

รัน: python3 -m model_c_event_clustering.scripts.e5_validate
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kruskal

from model_c_rulebase.engine.sector_rules import CHANNELS, MarketContext, StructuredVars, score_event
from model_c_rulebase.scripts.r5b_validate import CTX_PATH, VARS_PATH, run_engine_on_all_news

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "model_c_event_clustering" / "data"
ASSIGNMENTS_CSV = DATA_DIR / "e3_cluster_assignments.csv"
R5_RHO_TABLE = PROJECT_ROOT / "model_c_rulebase" / "data" / "r5_rho_table.csv"
OUT_CSV = DATA_DIR / "e5_test_results.csv"

P_THRESHOLD = 0.05
ETA_SQ_THRESHOLD = 0.06

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("e5_validate")


def eta_squared_kruskal(H: float, k: int, n: int) -> float:
    """ประมาณ eta-squared จากผล Kruskal-Wallis (Tomczak & Tomczak, 2014) —
    ตามที่ระบุไว้ใน PRE_REGISTERED_TEST.md ข้อ 3"""
    return (H - k + 1) / (n - k)


def run_engine_with_channels():
    """เหมือน run_engine_on_all_news() ของ exp_03 ทุกประการ แค่เก็บ channel contribution
    (C1-C7) เพิ่มด้วยสำหรับ secondary/exploratory test — ไม่แก้ r5b_validate.py ของ exp_03"""
    ctx = pd.read_csv(CTX_PATH)
    ctx["date"] = pd.to_datetime(ctx["date"])
    vars_df = pd.read_csv(VARS_PATH)
    vars_df["date"] = pd.to_datetime(vars_df["date"])
    vix_p90 = ctx["vix_delta"].quantile(0.90)
    merged = vars_df.merge(ctx, on=["date", "source", "url"], how="inner", suffixes=("", "_ctx"))

    from model_c_rulebase.engine.sector_rules import SECTORS

    rows = []
    for _, r in merged.iterrows():
        dxy = None if pd.isna(r["dxy_delta"]) else float(r["dxy_delta"])
        market = MarketContext(
            rate_surprise=float(r["rate_surprise"]), equity_move=float(r["equity_move"]),
            curve_slope_delta=float(r["curve_slope_delta"]), vix_delta=float(r["vix_delta"]),
            dxy_delta=dxy, shock_type=r["shock_type"],
        )
        llm = StructuredVars(
            stance_delta=int(r["stance_delta"]), growth_delta=int(r["growth_delta"]),
            inflation_delta=int(r["inflation_delta"]), labor_delta=int(r["labor_delta"]),
            forward_guidance_delta=int(r["forward_guidance_delta"]),
            balance_sheet_signal=int(r["balance_sheet_signal"]),
            uncertainty_language=int(r["uncertainty_language"]),
            financial_stability_concern=int(r["financial_stability_concern"]),
            low_confidence=bool(r["low_confidence"]),
        )
        result = score_event(market, llm, vix_p90)
        for sector in SECTORS:
            row = {"date": r["date"].date().isoformat(), "source": r["source"], "url": r["url"],
                    "sector": sector, "score": result["sectors"][sector]["score"]}
            row.update(result["sectors"][sector]["contributions"])
            rows.append(row)
    return pd.DataFrame(rows)


def run_kw_test(values_by_cluster: list) -> dict:
    groups = [v for v in values_by_cluster if len(v) > 0]
    k = len(groups)
    n = sum(len(v) for v in groups)

    all_values = np.concatenate(groups)
    if len(np.unique(all_values)) <= 1:
        # channel score เป็นค่าเดียวกันหมดทุกแถว (เช่น C3 ของ sector ที่ loading=0 ทุกกรณี) —
        # ไม่มี variance ให้ทดสอบเลย ไม่ใช่บั๊ก ไม่เดา p-value ใดๆ ทั้งสิ้น
        return {"H": np.nan, "p": np.nan, "eta_squared": np.nan, "k": k, "n": n, "passed": False,
                 "note": "no variance — channel นี้ = ค่าเดียวกันหมดสำหรับ sector นี้"}

    H, p = kruskal(*groups)
    eta_sq = eta_squared_kruskal(H, k, n)
    passed = (p < P_THRESHOLD) and (eta_sq > ETA_SQ_THRESHOLD)
    return {"H": H, "p": p, "eta_squared": eta_sq, "k": k, "n": n, "passed": passed, "note": ""}


def main():
    log.info("รัน rule engine จริง (เหมือน exp_03 R5b เป๊ะ, primary metric = sector_impact_score)")
    scores_primary = run_engine_on_all_news()  # date,source,url,sector,shock_type,low_confidence,score

    log.info("รัน engine อีกรอบพร้อมเก็บ channel contribution (C1-C7, secondary/exploratory)")
    scores_full = run_engine_with_channels()

    assignments = pd.read_csv(ASSIGNMENTS_CSV)
    log.info(f"cluster assignments (E3, sector เสถียรเท่านั้น): {len(assignments)} แถว, "
              f"{assignments['sector'].nunique()} sector")

    merged_primary = scores_primary.merge(
        assignments[["date", "source", "url", "sector", "cluster_k", "cluster_label"]],
        on=["date", "source", "url", "sector"], how="inner",
    )
    merged_full = scores_full.merge(
        assignments[["date", "source", "url", "sector", "cluster_k", "cluster_label"]],
        on=["date", "source", "url", "sector"], how="inner",
    )
    log.info(f"หลัง join กับ engine score: {len(merged_primary)} แถว (จาก {len(assignments)} ใน E3 — "
              f"ส่วนต่างคือข่าวที่ R3 สกัดไม่สำเร็จ [16 ข่าว: 452-436] หรือถูก E1 ตัดออกไปแล้วซ้อนกัน)")

    rho_table = pd.read_csv(R5_RHO_TABLE)

    results = []
    for sector, g in merged_primary.groupby("sector"):
        groups = [sub["score"].values for _, sub in g.groupby("cluster_label")]
        kw = run_kw_test(groups)

        channel_results = {}
        gc = merged_full[merged_full["sector"] == sector]
        for ch in CHANNELS:
            ch_groups = [sub[ch].values for _, sub in gc.groupby("cluster_label")]
            channel_results[ch] = run_kw_test(ch_groups)

        # rho_table มีหลายแถวต่อ sector (คนละ window) — ดึงมาทั้ง 3 หน้าต่างสำหรับ triangulation
        r5_rows_this_sector = rho_table[(rho_table["level"] == "by_sector") & (rho_table["group"] == sector)]

        results.append({
            "sector": sector, "n": kw["n"], "k_clusters": kw["k"],
            "H": kw["H"], "p": kw["p"], "eta_squared": kw["eta_squared"], "passed": kw["passed"],
            "r5_rho_n1": r5_rows_this_sector[r5_rows_this_sector["window"] == 1]["rho"].values[0]
                if len(r5_rows_this_sector[r5_rows_this_sector["window"] == 1]) else np.nan,
            "r5_rho_n21": r5_rows_this_sector[r5_rows_this_sector["window"] == 21]["rho"].values[0]
                if len(r5_rows_this_sector[r5_rows_this_sector["window"] == 21]) else np.nan,
            **{f"{ch}_p": channel_results[ch]["p"] for ch in CHANNELS},
            **{f"{ch}_eta_sq": channel_results[ch]["eta_squared"] for ch in CHANNELS},
            **{f"{ch}_passed": channel_results[ch]["passed"] for ch in CHANNELS},
        })

    results_df = pd.DataFrame(results).sort_values("sector")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(OUT_CSV, index=False)

    log.info("\n" + "=" * 90)
    log.info("SUMMARY — Phase E5 (primary test: sector_impact_score, ตาม PRE_REGISTERED_TEST.md)")
    log.info("=" * 90)
    for _, r in results_df.iterrows():
        status = "*** PASS ***" if r["passed"] else "fail"
        r5_agree = "n/a"
        if not pd.isna(r["r5_rho_n1"]):
            r5_flagged = abs(r["r5_rho_n1"]) > 0.3 or abs(r["r5_rho_n21"]) > 0.3
            r5_agree = "ขัดแย้งกับ R5 (R5 พบสัญญาณ)" if r5_flagged else "สอดคล้องกับ R5 (ทั้งคู่ negative)"
        log.info(f"  {r['sector']:5s} n={r['n']:4.0f} k={r['k_clusters']:.0f}  "
                  f"H={r['H']:.3f} p={r['p']:.4f} eta_sq={r['eta_squared']:+.4f}  {status}  "
                  f"| R5 rho(N=1)={r['r5_rho_n1']:+.3f} rho(N=21)={r['r5_rho_n21']:+.3f} -> {r5_agree}")

    n_pass = results_df["passed"].sum()
    log.info(f"\nจำนวน sector ที่ผ่านเกณฑ์ทั้ง 2 ข้อพร้อมกัน (p<{P_THRESHOLD} AND eta_sq>{ETA_SQ_THRESHOLD}): "
              f"{n_pass}/{len(results_df)}")
    if n_pass == 0:
        log.info("-> ไม่มี sector ไหนผ่านเกณฑ์เลย = NEGATIVE RESULT ยืนยัน exp_03/R5 ด้วยวิธีต่างไป")
    else:
        log.info(f"-> มี sector ผ่านเกณฑ์บางส่วน — ต้องตรวจ triangulation กับ R5 ก่อนสรุป (ดู log)")

    log.info(f"\nSaved -> {OUT_CSV}")
    return results_df


if __name__ == "__main__":
    main()
