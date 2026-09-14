"""
r5b_validate.py — Phase R5 (ส่วนที่ 2, "สำคัญที่สุด"): validation ของ rule engine กับ CAR จริง

**Protocol ที่กำหนดไว้ล่วงหน้าก่อนเห็นตัวเลขจริง (ห้ามเปลี่ยนหลังเห็นผล — ตามที่ระบุในเอกสาร
สเปก):**
    1. Metric หลัก: Spearman rank correlation ระหว่าง sector_impact_score กับ CAR จริง
       แยกตามหน้าต่าง (N=1/3/21) x sector x shock_type
    2. เกณฑ์ผ่าน: |rho| > 0.3 **และ** ดีกว่า baseline เดิม (exp_01/exp_02) อย่างชัดเจน
    3. Train/test split ตามเวลา: 452 ข่าวเรียงวันที่ 80% แรก=train, 20% ท้าย=test
       **ห้ามแตะ test set จนกว่า R6 calibration จะเสร็จ** — สคริปต์นี้จึงรายงานผลจาก TRAIN
       เท่านั้น (test set แค่รายงานขนาด ไม่แตะตัวเลขจริงใดๆ ของมัน)
    4. Unit of analysis: 452 ข่าว x 11 sector ไม่ใช่อิสระจากกัน (11 sector ในวันเดียวกันโดน
       event เดียวกันพร้อมกัน) -> ต้อง cluster โดย event date ตอนคำนวณ significance
    5. ไม่ผ่านเกณฑ์ = negative result ที่มีค่า ไม่ใช่ความล้มเหลว

**การตีความ "ดีกว่า baseline (exp_01, exp_02)":** exp_01/exp_02 เป็น multiclass classification
(accuracy/macro-F1) คนละ metric กับ Spearman rho ตรงนี้ เทียบตรงๆ ไม่ได้ในหน่วยเดียวกัน — แต่
`results.md` เดิมแสดงชัดว่า baseline ทั้งคู่ให้ accuracy ใกล้ random (~20-23%) และ exp_02 (+
sentiment) แย่กว่า exp_01 ด้วยซ้ำ กล่าวคือ **สัญญาณที่วัดได้จาก baseline เดิม ≈ ไม่มีเลย (เทียบเท่า
rho≈0)** ดังนั้นเกณฑ์ในข้อ 2 ("ดีกว่า baseline อย่างชัดเจน") ในทางปฏิบัติคือ: ถ้า cluster
bootstrap ยืนยันว่า rho แตกต่างจาก 0 อย่างมีนัยสำคัญ (CI ไม่คร่อม 0) นั่นก็ถือว่าดีกว่า baseline
เดิมโดยอัตโนมัติอยู่แล้ว (เพราะ baseline ไม่เคยแสดงสัญญาณที่ต่างจาก 0 อย่างมีนัยสำคัญเลย)

**Significance testing แบบ cluster (ตามข้อ 4):** ใช้ cluster bootstrap (resample ที่ระดับ "ข่าว"
ไม่ใช่ระดับแถว news x sector) หา 95% CI ของ rho — เคารพว่า 11 sector ของข่าวเดียวกันไม่อิสระจาก
กัน คำนวณเฉพาะระดับ pooled และ by-sector/by-shock_type (ระดับที่ตัดสิน pass/fail จริง) ส่วนตาราง
เต็ม sector x shock_type (55 ช่องต่อหน้าต่าง) รายงานแค่ rho + n เป็นข้อมูลเชิงสำรวจ (exploratory)
เพราะหลายช่องมี n เล็กเกินกว่าจะ bootstrap ได้น่าเชื่อถือ — ต้องรายงาน n กำกับทุกครั้งไม่ปิดบัง

Input:
    model_c_rulebase/data/fomc_market_context.csv   (R1+R2: market data + shock_type, 452 ข่าว)
    model_c_rulebase/data/fomc_structured_vars.csv   (R3: LLM structured vars, ~450 ข่าว ถ้าไม่มี
                                                        failure ระหว่างรัน — ข่าวที่ขาดจะไม่ถูก
                                                        นำเข้า engine เลย ไม่เดาค่าแทน)
    model_c_rulebase/data/car_windows.csv            (R5a: CAR จริง N=1/3/21, 4371 แถว)
Output:
    model_c_rulebase/data/r5_rho_table.csv           (ตารางเต็ม rho x n ทุก window x sector x shock_type)
    พิมพ์สรุปผลตัดสิน pass/fail ตาม protocol ทาง terminal

รัน: python3 -m model_c_rulebase.scripts.r5b_validate
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from model_c_rulebase.engine.sector_rules import SECTORS, MarketContext, StructuredVars, score_event

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CTX_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_market_context.csv"
VARS_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_structured_vars.csv"
CAR_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "car_windows.csv"
OUT_RHO_TABLE = PROJECT_ROOT / "model_c_rulebase" / "data" / "r5_rho_table.csv"

WINDOWS = [1, 3, 21]
TRAIN_FRAC = 0.8
PASS_THRESHOLD = 0.3
N_BOOT = 1000
BOOT_SEED = 42

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("r5b_validate")


# --------------------------------------------------------------------------
# Step 1: รัน rule engine จริงบนทุกข่าวที่มี structured vars (R3) ครบ
# --------------------------------------------------------------------------

def run_engine_on_all_news():
    ctx = pd.read_csv(CTX_PATH)
    ctx["date"] = pd.to_datetime(ctx["date"])

    vars_df = pd.read_csv(VARS_PATH)
    vars_df["date"] = pd.to_datetime(vars_df["date"])
    log.info(f"market context (R1+R2): {len(ctx)} ข่าว | structured vars (R3): {len(vars_df)} ข่าว")

    vix_p90 = ctx["vix_delta"].quantile(0.90)
    log.info(f"vix_delta 90th percentile (คำนวณจากข้อมูลจริง 452 ข่าว): {vix_p90:.4f}")

    merged = vars_df.merge(ctx, on=["date", "source", "url"], how="inner", suffixes=("", "_ctx"))
    n_dropped = len(vars_df) - len(merged)
    if n_dropped:
        log.warning(f"{n_dropped} ข่าวใน structured vars หา market context คู่กันไม่เจอ (ผิดปกติ — ตรวจสอบ)")

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
            rows.append({
                "date": r["date"].date().isoformat(), "source": r["source"], "url": r["url"],
                "sector": sector, "shock_type": r["shock_type"],
                "low_confidence": bool(r["low_confidence"]),
                "score": result["sectors"][sector]["score"],
            })

    scores_df = pd.DataFrame(rows)
    log.info(f"รัน engine สำเร็จ: {merged.shape[0]} ข่าว x {len(SECTORS)} sector = {len(scores_df)} แถว")
    return scores_df


# --------------------------------------------------------------------------
# Step 2: train/test split ตามเวลา (80/20 บนหน่วย "ข่าว" ไม่ใช่หน่วยแถว)
# --------------------------------------------------------------------------

def assign_time_split(scores_df):
    unique_news = scores_df[["date"]].drop_duplicates().sort_values("date").reset_index(drop=True)
    n_news = len(unique_news)
    cutoff_idx = int(n_news * TRAIN_FRAC)
    cutoff_date = unique_news.iloc[cutoff_idx]["date"] if cutoff_idx < n_news else unique_news.iloc[-1]["date"]

    scores_df = scores_df.copy()
    scores_df["r5_split"] = np.where(scores_df["date"] < cutoff_date, "train", "test")

    n_train_news = (unique_news["date"] < cutoff_date).sum()
    n_test_news = n_news - n_train_news
    log.info(f"R5 time split: {n_news} ข่าว unique -> train {n_train_news} ({n_train_news/n_news*100:.1f}%), "
             f"test {n_test_news} ({n_test_news/n_news*100:.1f}%), cutoff date = {cutoff_date}")
    return scores_df


# --------------------------------------------------------------------------
# Step 3: cluster bootstrap ของ Spearman rho (resample ที่ระดับข่าว)
# --------------------------------------------------------------------------

def cluster_bootstrap_rho(df, score_col, car_col, date_col="date", n_boot=N_BOOT, seed=BOOT_SEED):
    """คืน (rho_observed, ci_lo, ci_hi, n_events, n_rows) จาก cluster bootstrap โดย resample
    ที่ระดับ "วันข่าว" (event date) ตามข้อกำหนดข้อ 4 (11 sector ของข่าวเดียวกันไม่อิสระจากกัน)"""
    d = df.dropna(subset=[score_col, car_col])
    if d[score_col].nunique() < 2 or d[car_col].nunique() < 2 or len(d) < 4:
        return None, None, None, d[date_col].nunique(), len(d)

    rho_obs = spearmanr(d[score_col], d[car_col]).correlation

    events = d[date_col].unique()
    event_to_rows = {e: d.index[d[date_col] == e].to_numpy() for e in events}
    score_arr = d[score_col].to_numpy()
    car_arr = d[car_col].to_numpy()
    row_pos = {idx: i for i, idx in enumerate(d.index)}

    rng = np.random.default_rng(seed)
    boot_rhos = []
    for _ in range(n_boot):
        sampled_events = rng.choice(events, size=len(events), replace=True)
        idxs = np.concatenate([event_to_rows[e] for e in sampled_events])
        positions = [row_pos[i] for i in idxs]
        s = score_arr[positions]
        c = car_arr[positions]
        if len(set(s.tolist())) < 2 or len(set(c.tolist())) < 2:
            continue
        r = spearmanr(s, c).correlation
        if not np.isnan(r):
            boot_rhos.append(r)

    if len(boot_rhos) < n_boot * 0.5:
        return rho_obs, None, None, len(events), len(d)

    ci_lo, ci_hi = np.percentile(boot_rhos, [2.5, 97.5])
    return rho_obs, ci_lo, ci_hi, len(events), len(d)


# --------------------------------------------------------------------------
# Step 4: join กับ CAR แล้วสร้างตาราง rho เต็ม (window x sector x shock_type) — TRAIN เท่านั้น
# --------------------------------------------------------------------------

def build_rho_table(scores_df, car_df):
    car_df = car_df.copy()
    merged = scores_df.merge(
        car_df[["date", "source", "url", "sector", "car_n1", "car_n3", "car_n21"]],
        on=["date", "source", "url", "sector"], how="inner",
    )
    n_dropped = len(scores_df) - len(merged)
    if n_dropped:
        log.warning(f"{n_dropped} แถว score หา CAR คู่กันไม่เจอ (ตรวจสอบ join key)")

    train = merged[merged["r5_split"] == "train"].copy()
    test = merged[merged["r5_split"] == "test"].copy()
    log.info(f"หลัง join กับ CAR: train={len(train)} แถว ({train['date'].nunique()} ข่าว), "
             f"test={len(test)} แถว ({test['date'].nunique()} ข่าว, **ไม่แตะตัวเลขในเฟสนี้**)")

    results = []

    for n in WINDOWS:
        car_col = f"car_n{n}"

        rho, lo, hi, n_ev, n_rows = cluster_bootstrap_rho(train, "score", car_col)
        results.append({"window": n, "level": "pooled", "group": "ALL", "rho": rho,
                          "ci_lo": lo, "ci_hi": hi, "n_events": n_ev, "n_rows": n_rows})

        for sector in SECTORS:
            sub = train[train["sector"] == sector]
            rho, lo, hi, n_ev, n_rows = cluster_bootstrap_rho(sub, "score", car_col)
            results.append({"window": n, "level": "by_sector", "group": sector, "rho": rho,
                              "ci_lo": lo, "ci_hi": hi, "n_events": n_ev, "n_rows": n_rows})

        for shock in train["shock_type"].unique():
            sub = train[train["shock_type"] == shock]
            rho, lo, hi, n_ev, n_rows = cluster_bootstrap_rho(sub, "score", car_col)
            results.append({"window": n, "level": "by_shock_type", "group": shock, "rho": rho,
                              "ci_lo": lo, "ci_hi": hi, "n_events": n_ev, "n_rows": n_rows})

        # ตารางเต็ม sector x shock_type — exploratory เท่านั้น (n เล็ก, ไม่ bootstrap เพื่อความเร็ว
        # และเพราะ CI จาก n น้อยไม่น่าเชื่อถือพอจะรายงานเป็นทางการ — รายงานแค่ rho + n ตรงไปตรงมา)
        for sector in SECTORS:
            for shock in train["shock_type"].unique():
                sub = train[(train["sector"] == sector) & (train["shock_type"] == shock)]
                d = sub.dropna(subset=["score", car_col])
                if d["score"].nunique() < 2 or d[car_col].nunique() < 2 or len(d) < 4:
                    rho = None
                else:
                    rho = spearmanr(d["score"], d[car_col]).correlation
                results.append({"window": n, "level": "sector_x_shock", "group": f"{sector}|{shock}",
                                  "rho": rho, "ci_lo": None, "ci_hi": None,
                                  "n_events": len(d), "n_rows": len(d)})

    return pd.DataFrame(results), train, test


def main():
    scores_df = run_engine_on_all_news()
    scores_df = assign_time_split(scores_df)

    car_df = pd.read_csv(CAR_PATH)

    rho_table, train, test = build_rho_table(scores_df, car_df)
    rho_table.to_csv(OUT_RHO_TABLE, index=False)

    log.info("=" * 70)
    log.info("SUMMARY — Phase R5: Pooled + by-sector + by-shock_type rho (TRAIN ONLY)")
    log.info("=" * 70)

    passing = []
    for n in WINDOWS:
        pooled = rho_table[(rho_table["window"] == n) & (rho_table["level"] == "pooled")].iloc[0]
        log.info(f"\n--- N={n} วัน ---")
        log.info(f"  POOLED: rho={pooled['rho']:+.4f} 95%CI=[{pooled['ci_lo']:+.4f}, {pooled['ci_hi']:+.4f}] "
                  f"(n_events={pooled['n_events']}, n_rows={pooled['n_rows']})")

        for level in ["by_sector", "by_shock_type"]:
            sub = rho_table[(rho_table["window"] == n) & (rho_table["level"] == level)]
            for _, r in sub.sort_values("rho", key=lambda s: s.abs(), ascending=False).iterrows():
                n_events = r["n_events"]
                has_ci = r["ci_lo"] is not None and r["ci_hi"] is not None and not pd.isna(r["ci_lo"])
                if n_events < 10 or r["rho"] is None or pd.isna(r["rho"]):
                    sig = "n เล็กเกินไปจะสรุป (n_events<10 หรือ rho คำนวณไม่ได้)"
                elif has_ci:
                    crosses_zero = r["ci_lo"] <= 0 <= r["ci_hi"]
                    sig = "NOT sig (CI crosses 0)" if crosses_zero else "significant (CI excludes 0)"
                else:
                    sig = "bootstrap ไม่พอ (nan มากเกินไป)"
                passed = (r["rho"] is not None and not pd.isna(r["rho"])
                          and abs(r["rho"]) > PASS_THRESHOLD and n_events >= 10)
                if passed and sig.startswith("significant"):
                    passing.append((n, level, r["group"], r["rho"]))
                ci_str = f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]" if has_ci else "(n/a)"
                rho_str = f"{r['rho']:+.4f}" if r["rho"] is not None and not pd.isna(r["rho"]) else "n/a"
                log.info(f"    {level}={r['group']:20s} rho={rho_str} 95%CI={ci_str} "
                          f"n_events={n_events:4.0f} {'*** |rho|>0.3 ***' if passed else ''} {sig}")

    log.info("\n" + "=" * 70)
    log.info("PASS/FAIL ตามเกณฑ์ที่กำหนดไว้ล่วงหน้า: |rho|>0.3 AND CI ไม่คร่อม 0 (=ดีกว่า baseline "
              "ที่ไม่เคยแสดงสัญญาณต่างจาก 0 อย่างมีนัยสำคัญเลย)")
    log.info("=" * 70)
    if passing:
        log.info(f"ผ่านเกณฑ์ {len(passing)} รายการ:")
        for n, level, group, rho in passing:
            log.info(f"  N={n}, {level}={group}: rho={rho:+.4f}")
    else:
        log.info("ไม่มีรายการไหนผ่านเกณฑ์ทั้งสองข้อพร้อมกันเลย (ทั้ง pooled, by_sector, by_shock_type)")
        log.info("-> NEGATIVE RESULT ตามที่ระบุไว้ในสเปกว่า 'มีค่า ไม่ใช่ความล้มเหลว' — ดูรายละเอียด "
                  "การตีความใน experiments/log.md")

    log.info(f"\nTest set (ยังไม่แตะตัวเลขใดๆ ตาม protocol): {test['date'].nunique()} ข่าว, {len(test)} แถว")
    log.info(f"Rho table เต็ม (รวม sector x shock_type breakdown) -> {OUT_RHO_TABLE}")

    return rho_table


if __name__ == "__main__":
    main()
