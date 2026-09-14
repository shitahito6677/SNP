"""
e1_price_paths.py — exp_04 Phase E1: ดึง price path รายวัน (ไม่ใช่แค่ endpoint แบบ CAR เดิม)
สำหรับข่าว FOMC/Beige Book โดยให้ window ยาว-สั้นอัตโนมัติต่อข่าว กัน window ทับกันระหว่างข่าว
ที่ออกถี่ (Beige Book ก่อน FOMC ถัดไปแค่ ~2 สัปดาห์โดยเฉลี่ย)

**บริบท:** `exp_03` สรุปว่าไม่มีสัญญาณระดับ sector จาก endpoint เดียว (CAR ณ N=1/3/21 วัน)
`exp_04` นี้ถามคำถามคนละมุม — ดู "รูปร่าง" ของเส้นราคาทั้งเส้น (สะสมทุกวัน ไม่ใช่แค่จุดเดียว)
ว่ามี pattern ที่แยกกลุ่มได้มั้ย เป้าหมายคือ **triangulate** ผลลบเดิมด้วยวิธีต่างไป ไม่ใช่หา
ผลบวกให้ได้

**Window sizing (ป้องกัน overlap):**
    window_days = min(FIXED_MAX_WINDOW=10,
                       (next_event_date - event_date).days // 2,
                       (event_date - prev_event_date).days // 2)
คำนวณจาก **ลำดับข่าวรวมทุก source** (FOMC + Beige Book ผสมกันเรียงตามวันที่) ไม่ใช่แยกต่อ source
เพราะปัญหา overlap เกิดจากทั้งสอง source ออกสลับกันถี่ ไม่ใช่แค่ source เดียวกันชนกันเอง
ข่าวที่ window_days < 5 -> ตัดออกทั้งข่าว (ทุก sector) ไม่ยัดเข้าไป ไม่เดา — log เหตุผลไว้

**นิยาม cumulative abnormal return (`cum_ar`) — ต้องระบุให้ชัด (ไม่ใช่สิ่งที่ตัวโจทย์กำหนดตายตัว
มาให้ ต้องตัดสินใจเอง เขียนไว้ตรงนี้กันงงตอนใช้ต่อใน E2):**
    - t0 = trading day แรกของ SPY calendar ที่ >= วันข่าว (คอนเวนชันเดียวกับ R1/R5 เดิม)
    - cum_ar[0] = 0 เสมอ (baseline ที่ t0 เอง)
    - cum_ar[offset] สำหรับ offset > 0 (หลังข่าว) = ผลรวม daily abnormal return (sector − SPY)
      จาก t0+1 ถึง t0+offset (นับตาม trading day ไม่ใช่ calendar day) — สูตรเดียวกับ CAR เดิม
      ของ exp_01/exp_02/exp_03 ทุกประการ แค่เก็บทุกวันแทนที่จะเก็บแค่ endpoint
    - cum_ar[offset] สำหรับ offset < 0 (ก่อนข่าว) = −(ผลรวม daily abnormal return จาก t0+offset+1
      ถึง t0) — ทำให้ cum_ar เป็นเส้นต่อเนื่องผ่าน 0 ที่ t0 พอดี (ตาม convention การวาดกราฟ event
      study ทั่วไป) เห็น drift ก่อนข่าว + ปฏิกิริยาหลังข่าวบนสเกลเดียวกัน

Input : data/processed/labels.parquet (452 ข่าว x source x url เดิมจาก exp_01-03, ไม่แก้)
        model_c_rulebase/data/*price* หรือดึงจาก yfinance ใหม่ (ใช้ cache เดิมถ้ามี ประหยัดเวลา)
Output: model_c_event_clustering/data/price_paths.csv
        (1 แถว = 1 ข่าว x 1 sector x 1 trading-day offset)
        model_c_event_clustering/data/e1_excluded_news.csv (ข่าวที่ถูกตัดออก + เหตุผล)

รัน: python3 -m model_c_event_clustering.scripts.e1_price_paths
"""

import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LABELS_PATH = PROJECT_ROOT / "data" / "processed" / "labels.parquet"
PRICE_CACHE_PATH = PROJECT_ROOT / "data" / "raw" / "sector_prices_raw.parquet"
OUT_DIR = PROJECT_ROOT / "model_c_event_clustering" / "data"
OUT_PATHS = OUT_DIR / "price_paths.csv"
OUT_EXCLUDED = OUT_DIR / "e1_excluded_news.csv"

SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
BENCHMARK = "SPY"

FIXED_MAX_WINDOW = 10   # calendar days, ค่าสูงสุดที่ปลอดภัย
MIN_WINDOW = 5          # calendar days, ต่ำกว่านี้ตัดข่าวทิ้งทั้งหมด (ทุก sector)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("e1_price_paths")


def load_news():
    labels = pd.read_parquet(LABELS_PATH)
    news = labels[["date", "source", "url"]].drop_duplicates().sort_values("date").reset_index(drop=True)
    news["date"] = pd.to_datetime(news["date"])
    return news


def compute_window_days(news: pd.DataFrame) -> pd.DataFrame:
    """คำนวณ window_days ต่อข่าว จากลำดับข่าวรวมทุก source (ตามที่ระบุ) คืน DataFrame เดิม + คอลัมน์
    window_days ใหม่"""
    dates = news["date"].values
    n = len(dates)
    window_days = []
    for i in range(n):
        candidates = [FIXED_MAX_WINDOW]
        if i > 0:
            gap_prev = (dates[i] - dates[i - 1]).astype("timedelta64[D]").astype(int)
            candidates.append(gap_prev // 2)
        if i < n - 1:
            gap_next = (dates[i + 1] - dates[i]).astype("timedelta64[D]").astype(int)
            candidates.append(gap_next // 2)
        window_days.append(min(candidates))
    news = news.copy()
    news["window_days"] = window_days
    return news


def build_price_paths(news: pd.DataFrame, close: pd.DataFrame):
    master_calendar = close[BENCHMARK].dropna().index
    n_cal = len(master_calendar)
    returns = close.pct_change()

    included_rows = []
    excluded = []

    for _, r in news.iterrows():
        if r["window_days"] < MIN_WINDOW:
            excluded.append({"date": r["date"].date().isoformat(), "source": r["source"],
                              "url": r["url"], "window_days": r["window_days"],
                              "reason": f"window_days={r['window_days']} < ขั้นต่ำ {MIN_WINDOW} วัน"})
            continue

        news_date = r["date"]
        window_days = r["window_days"]
        pos = master_calendar.searchsorted(news_date)
        if pos >= n_cal:
            excluded.append({"date": news_date.date().isoformat(), "source": r["source"],
                              "url": r["url"], "window_days": window_days,
                              "reason": "หา t0 ใน master calendar ไม่ได้ (นอก range ราคาที่มี)"})
            continue
        idx0 = pos
        t0 = master_calendar[idx0]

        win_start = news_date - pd.Timedelta(days=window_days)
        win_end = news_date + pd.Timedelta(days=window_days)
        window_dates = master_calendar[(master_calendar >= win_start) & (master_calendar <= win_end)]

        if t0 not in window_dates or len(window_dates) < 2:
            excluded.append({"date": news_date.date().isoformat(), "source": r["source"],
                              "url": r["url"], "window_days": window_days,
                              "reason": "ไม่มี trading day พอในช่วง window ที่คำนวณได้"})
            continue

        pre_dates = window_dates[window_dates < t0]
        post_dates = window_dates[window_dates > t0]

        if close.loc[window_dates, BENCHMARK].isna().any():
            excluded.append({"date": news_date.date().isoformat(), "source": r["source"],
                              "url": r["url"], "window_days": window_days,
                              "reason": "SPY มีราคาขาดหายในช่วง window"})
            continue

        for sector in SECTORS:
            if sector not in close.columns or close.loc[window_dates, sector].isna().any():
                continue  # sector นี้ไม่มีราคาครบในช่วงนี้ (เช่น ETF ยังไม่เปิดตัว) ข้ามแค่ sector นี้

            ar = (returns[sector] - returns[BENCHMARK]).loc[window_dates]

            # cum_ar หลัง t0: cumsum ปกติจาก t0+1 เป็นต้นไป
            post_ar = ar.loc[post_dates]
            post_cum = post_ar.cumsum()

            # cum_ar ก่อน t0: ทำให้ต่อเนื่องผ่าน 0 ที่ t0 (สะสม "ถอยหลัง" จาก t0)
            pre_ar_reversed = ar.loc[pre_dates][::-1]  # จาก t0-1 ย้อนไปหา window start
            pre_cum_reversed = pre_ar_reversed.cumsum()
            pre_cum = (-pre_cum_reversed)[::-1]  # กลับมาเรียงตามเวลาปกติ, ติดลบตามนิยาม

            for offset, d in enumerate(pre_dates, start=-len(pre_dates)):
                included_rows.append({
                    "date": news_date.date().isoformat(), "source": r["source"], "url": r["url"],
                    "sector": sector, "window_days": window_days, "t0": t0.date().isoformat(),
                    "trading_date": d.date().isoformat(), "offset": offset,
                    "daily_ar": float(ar.loc[d]), "cum_ar": float(pre_cum.loc[d]),
                })
            included_rows.append({
                "date": news_date.date().isoformat(), "source": r["source"], "url": r["url"],
                "sector": sector, "window_days": window_days, "t0": t0.date().isoformat(),
                "trading_date": t0.date().isoformat(), "offset": 0,
                "daily_ar": 0.0, "cum_ar": 0.0,
            })
            for offset, d in enumerate(post_dates, start=1):
                included_rows.append({
                    "date": news_date.date().isoformat(), "source": r["source"], "url": r["url"],
                    "sector": sector, "window_days": window_days, "t0": t0.date().isoformat(),
                    "trading_date": d.date().isoformat(), "offset": offset,
                    "daily_ar": float(ar.loc[d]), "cum_ar": float(post_cum.loc[d]),
                })

    return pd.DataFrame(included_rows), pd.DataFrame(excluded)


def main():
    news = load_news()
    log.info(f"โหลดข่าว {len(news)} รายการ")

    news = compute_window_days(news)
    log.info(f"window_days: min={news['window_days'].min()}, median={news['window_days'].median()}, "
              f"max={news['window_days'].max()}")

    close = pd.read_parquet(PRICE_CACHE_PATH).sort_index()
    log.info(f"โหลด price cache: {len(close)} trading days")

    paths_df, excluded_df = build_price_paths(news, close)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths_df.to_csv(OUT_PATHS, index=False)
    excluded_df.to_csv(OUT_EXCLUDED, index=False)

    n_included_news = paths_df[["date", "source", "url"]].drop_duplicates().shape[0]
    log.info("=" * 60)
    log.info("SUMMARY — Phase E1")
    log.info("=" * 60)
    log.info(f"ข่าวทั้งหมด: {len(news)}")
    log.info(f"ข่าวที่ถูกตัดออก (window_days < {MIN_WINDOW} หรือราคาไม่ครบ): {len(excluded_df)}")
    if len(excluded_df):
        log.info("เหตุผลที่ตัดออก:")
        for reason, n in excluded_df["reason"].value_counts().items():
            log.info(f"  {reason}: {n}")
    log.info(f"ข่าวที่เหลือ (มี price path): {n_included_news}")
    log.info(f"แถวรวม (ข่าว x sector x offset): {len(paths_df)}")
    log.info(f"Saved -> {OUT_PATHS}")
    log.info(f"Saved -> {OUT_EXCLUDED}")
    return paths_df, excluded_df


if __name__ == "__main__":
    main()
