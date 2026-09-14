"""
r5a_car_windows.py — Phase R5 (ส่วนที่ 1): เพิ่ม CAR หน้าต่างสั้น N=1, N=3 วันทำการ ควบคู่กับ
N=21 เดิมจาก exp_01/exp_02 (`data/processed/labels.parquet`) — สูตรเดียวกันเป๊ะ (cumulative
abnormal return แบบ Brown & Warner 1985, สมมติ beta=1 ลบ SPY ตรงๆ) แค่เปลี่ยนช่วง t ไม่คำนวณ
ใหม่ตั้งแต่ต้น ไม่สร้าง label ใหม่ — ใช้ label/สังกัด train-test เดิมจาก exp_01/exp_02 ทุกจุด

เหตุผลที่ต้องมี N สั้น (จากเอกสารสเปก): "สัญญาณจาก FOMC มักจางเร็ว งานวิจัยส่วนใหญ่ใช้หน้าต่าง
สั้นกว่า N=21 (ธรรมเนียม ~1 เดือนปฏิทิน) มาก การสะสมยาวถึง 21 วันเสี่ยงให้ noise จาก 18 วันหลัง
กลบสัญญาณจริงในช่วงแรก" — R5 (ในสคริปต์ถัดไป r5b) จะทดสอบทั้ง 3 หน้าต่างเทียบกันตามที่กำหนด

วิธีคำนวณ (คัดลอกจาก src/s2_build_labels.py ทุกจุดที่เกี่ยวกับ t0/calendar เพื่อให้ t0 ตรงกันเป๊ะ
กับที่ label เดิมใช้ — ไม่ recompute จาก 0 ทั้งไฟล์ ใช้ (date, source, url) ของ labels.parquet
เป็น anchor แล้วหา t0 ใหม่ด้วย logic เดียวกัน จาก data/raw/sector_prices_raw.parquet ที่แคชไว้
อยู่แล้วจาก exp_01/exp_02):
    1. t0 = trading day แรกใน master calendar (SPY) ที่ >= วันข่าว (เหมือน s2_build_labels.py)
    2. CAR(N) = Σ [r_sector,t − r_SPY,t] สำหรับ t = t0+1 .. t0+N trading days
    3. คำนวณ N=1, 3, 21 ด้วย t0 เดียวกัน — ตรวจสอบว่า N=21 ที่ recompute ตรงกับ 'score' เดิมใน
       labels.parquet เป๊ะ (sanity check ว่า t0/calendar logic ตรงกันจริง ไม่ใช่แค่คิดว่าตรง)

ข้อจำกัดที่ต้องรู้ (ตามที่ระบุในสเปก, ไม่ใช่เรื่องใหม่ที่ script นี้สร้างขึ้น):
    - สมมติ beta=1 ทุก sector (ลบ SPY ตรงๆ ไม่ปรับ beta จริง) — sector ที่ beta ต่างจาก 1 มาก
      (เช่น XLU beta ต่ำ, XLK beta สูง) อาจมี systematic bias ติดมาใน CAR ที่ไม่ได้มาจากข่าวล้วนๆ
    - N=21 มาจากธรรมเนียม ไม่ใช่ค่าที่พิสูจน์แล้วว่าเหมาะกับ FOMC โดยเฉพาะ

Output: model_c_rulebase/data/car_windows.csv
    (date, source, url, sector, split, label_n21_quantile, car_n1, car_n3, car_n21)

รัน: python3 -m model_c_rulebase.scripts.r5a_car_windows
"""

import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LABELS_PATH = PROJECT_ROOT / "data" / "processed" / "labels.parquet"
PRICE_CACHE_PATH = PROJECT_ROOT / "data" / "raw" / "sector_prices_raw.parquet"
OUT_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "car_windows.csv"

SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
BENCHMARK = "SPY"
WINDOWS = [1, 3, 21]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("r5a_car_windows")


def main():
    labels = pd.read_parquet(LABELS_PATH)
    labels["date"] = pd.to_datetime(labels["date"])
    log.info(f"Loaded {len(labels)} label rows (news x sector) จาก {LABELS_PATH}")

    close = pd.read_parquet(PRICE_CACHE_PATH)
    close = close.sort_index()
    returns = close.pct_change()
    master_calendar = close[BENCHMARK].dropna().index
    n_cal = len(master_calendar)
    log.info(f"Loaded price cache: {len(close)} trading days, master calendar (SPY) = {n_cal} วัน")

    max_window = max(WINDOWS)
    rows = []
    skipped = 0

    for _, r in labels.iterrows():
        news_date = r["date"]
        pos = master_calendar.searchsorted(news_date)
        if pos >= n_cal or pos + max_window >= n_cal:
            skipped += 1
            continue
        idx0 = pos
        sector = r["sector"]
        if sector not in returns.columns:
            skipped += 1
            continue

        post_dates_all = master_calendar[idx0 + 1: idx0 + max_window + 1]
        sec_ret = returns.loc[post_dates_all, sector]
        spy_ret = returns.loc[post_dates_all, BENCHMARK]
        if sec_ret.isna().any() or spy_ret.isna().any():
            skipped += 1
            continue
        excess = (sec_ret - spy_ret).values

        row = {
            "date": r["date"].date().isoformat(), "source": r["source"], "url": r["url"],
            "sector": sector, "split": r["split"], "label_n21_quantile": int(r["label"]),
        }
        for n in WINDOWS:
            row[f"car_n{n}"] = float(excess[:n].sum())
        rows.append(row)

    df = pd.DataFrame(rows)
    log.info(f"สร้างได้ {len(df)} แถว, ข้าม {skipped} แถว (ราคาไม่ครบในหน้าต่างที่ยาวที่สุด N={max_window})")

    # sanity check: N=21 ที่ recompute ต้องตรงกับ 'score' เดิมใน labels.parquet เป๊ะ (ไม่ใช่แค่คิด
    # ว่า t0/calendar logic เดียวกัน — ต้องยืนยันด้วยตัวเลขจริง)
    merged_check = df.merge(
        labels[["date", "source", "url", "sector", "score"]],
        left_on=["date", "source", "url", "sector"],
        right_on=[labels["date"].dt.date.astype(str), "source", "url", "sector"],
        suffixes=("", "_orig"),
    )
    diff = (merged_check["car_n21"] - merged_check["score"]).abs()
    max_diff = diff.max()
    log.info(f"Sanity check: recompute N=21 vs 'score' เดิมใน labels.parquet — "
             f"max abs diff = {max_diff:.10f} ({len(merged_check)} แถวเทียบได้)")
    if max_diff > 1e-9:
        raise RuntimeError(
            f"N=21 ที่ recompute ไม่ตรงกับ labels.parquet เดิม (max diff={max_diff}) — "
            f"t0/calendar logic ต้องมีจุดต่างจาก s2_build_labels.py ห้ามไปต่อจนกว่าจะหาสาเหตุเจอ"
        )
    log.info("PASS: N=21 recompute ตรงกับ labels.parquet เดิมเป๊ะ — t0/calendar logic ถูกต้อง")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)

    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"แถวทั้งหมด: {len(df)} (news x sector), unique news: {df[['date','source','url']].drop_duplicates().shape[0]}")
    for n in WINDOWS:
        log.info(f"CAR N={n:2d}: mean={df[f'car_n{n}'].mean():+.5f}, std={df[f'car_n{n}'].std():.5f}, "
                  f"min={df[f'car_n{n}'].min():+.5f}, max={df[f'car_n{n}'].max():+.5f}")
    log.info(f"Saved -> {OUT_PATH}")
    return df


if __name__ == "__main__":
    main()
