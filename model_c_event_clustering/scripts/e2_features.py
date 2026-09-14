"""
e2_features.py — exp_04 Phase E2: สกัด feature จาก price path (E1) ต่อ (ข่าว x sector)

**เหตุผลที่ไม่ clustering ราคาดิบตรงๆ:** ราคาดิบ (cum_ar ต่อวัน) เป็น time series ที่ noise สูง
และมีความยาวต่างกันตาม `window_days` ของแต่ละข่าว — ต้องสรุปเป็น feature ที่ตายตัว (fixed
dimension) ก่อนถึงจะ clustering ได้อย่างมีความหมาย (K-means/hierarchical ต้องการ vector ความยาว
เท่ากันทุกจุดข้อมูล)

Feature ที่สกัด (ต่อ 1 แถว = 1 ข่าว x 1 sector, อิง `cum_ar` ที่นิยามไว้ใน E1 — ต่อเนื่องผ่าน 0
ที่ `t0`):
    - `cum_return_pre`       = cum_ar ที่ offset = -1 (วันสุดท้ายก่อนข่าว — ค่านี้เท่ากับ
      cumulative drift สะสมทั้งช่วง pre-window อยู่แล้วในตัว เพราะ cum_ar สร้างจาก cumsum)
    - `cum_return_post_short`= cum_ar ที่ offset = +3 ถ้ามี (บาง (ข่าว,sector) window แคบกว่า
      3 trading day ฝั่ง post จริง ๆ — กรณีนี้เก็บเป็น NaN ไม่เดา/ไม่ใช้ offset ใกล้เคียงแทน)
    - `cum_return_post_full` = cum_ar ที่ offset สูงสุดที่มีจริงฝั่ง post (ปลายหน้าต่าง)
    - `peak_offset`          = offset (เฉพาะฝั่ง post, 1..max) ที่ cum_ar ไปถึงจุดสุดขั้วใน
      "ทิศทางเดียวกับการเคลื่อนไหวสุทธิ" (ถ้า cum_return_post_full >= 0 หา offset ที่ cum_ar
      สูงสุด, ถ้า < 0 หา offset ที่ cum_ar ต่ำสุด) — ตรงกับนิยาม "peak_day" ในสเปก
    - `reversion_ratio`      = cum_return_post_full ÷ cum_ar ที่ peak_offset (ถ้าค่า peak ≈ 0
      เป๊ะ [ต่ำกว่า 1e-6] ให้เป็น NaN ไม่หารด้วยเลขใกล้ 0 จนได้ค่าพิสดาร)

Input : model_c_event_clustering/data/price_paths.csv (จาก E1)
Output: model_c_event_clustering/data/event_features.csv (1 แถว ต่อ ข่าว x sector)

รัน: python3 -m model_c_event_clustering.scripts.e2_features
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "model_c_event_clustering" / "data"
PATHS_CSV = DATA_DIR / "price_paths.csv"
OUT_CSV = DATA_DIR / "event_features.csv"

ZERO_EPS = 1e-6

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("e2_features")


def extract_features(group: pd.DataFrame) -> dict:
    g = group.set_index("offset").sort_index()

    cum_return_pre = g.loc[-1, "cum_ar"] if -1 in g.index else np.nan

    cum_return_post_short = g.loc[3, "cum_ar"] if 3 in g.index else np.nan

    post = g[g.index > 0]
    if post.empty:
        return None  # ไม่ควรเกิด (E1 กันไว้แล้วว่าต้องมี post >= 1 วัน) เผื่อไว้

    cum_return_post_full = post["cum_ar"].iloc[-1]

    if cum_return_post_full >= 0:
        peak_offset = post["cum_ar"].idxmax()
    else:
        peak_offset = post["cum_ar"].idxmin()
    peak_value = post.loc[peak_offset, "cum_ar"]

    if abs(peak_value) < ZERO_EPS:
        reversion_ratio = np.nan
    else:
        reversion_ratio = cum_return_post_full / peak_value

    return {
        "cum_return_pre": cum_return_pre,
        "cum_return_post_short": cum_return_post_short,
        "cum_return_post_full": cum_return_post_full,
        "peak_offset": int(peak_offset),
        "peak_value": peak_value,
        "reversion_ratio": reversion_ratio,
    }


def main():
    paths = pd.read_csv(PATHS_CSV)
    log.info(f"โหลด price path {len(paths)} แถว")

    rows = []
    for (date, source, url, sector), group in paths.groupby(["date", "source", "url", "sector"]):
        feats = extract_features(group)
        if feats is None:
            continue
        rows.append({"date": date, "source": source, "url": url, "sector": sector, **feats})

    features_df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    features_df.to_csv(OUT_CSV, index=False)

    log.info("=" * 60)
    log.info("SUMMARY — Phase E2")
    log.info("=" * 60)
    log.info(f"แถว feature ทั้งหมด (ข่าว x sector): {len(features_df)}")
    log.info(f"ข่าว unique: {features_df[['date','source','url']].drop_duplicates().shape[0]}")
    log.info(f"cum_return_post_short เป็น NaN (window แคบกว่า 3 วัน post จริง): "
              f"{features_df['cum_return_post_short'].isna().sum()}")
    log.info(f"reversion_ratio เป็น NaN (peak ≈ 0): {features_df['reversion_ratio'].isna().sum()}")
    for col in ["cum_return_pre", "cum_return_post_short", "cum_return_post_full", "reversion_ratio"]:
        log.info(f"{col}: mean={features_df[col].mean():+.5f}, std={features_df[col].std():.5f}")
    log.info(f"Saved -> {OUT_CSV}")
    return features_df


if __name__ == "__main__":
    main()
