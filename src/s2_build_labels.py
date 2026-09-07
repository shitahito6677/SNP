"""
s2_build_labels.py — ขั้นที่ 2: สร้าง label ผลกระทบของข่าวมหภาคต่อแต่ละ GICS sector

Input : data/raw/macro_news_raw.parquet   (จาก s1_fetch_news.py)
Output: data/processed/labels.parquet     (1 แถว = 1 ข่าว x 1 sector)

วิธีคำนวณ (event-study cumulative abnormal return):
    1. ดึงราคาปิด (adjusted close, yfinance) ของ SPY + sector ETF ทั้ง 11 ตัว
    2. t0 = trading day แรกที่ >= วันที่ข่าว (ใช้ trading-day calendar ของ SPY เป็น master)
    3. ต้องมีราคาปิดครบทุก trading day ในช่วง [t0-30, t0+30] (61 วัน) ทั้งของ sector และ SPY
       ตามที่โจทย์กำหนด — ถ้าข้อมูลราคาขาดช่วงไหน (เช่น sector ETF ยังไม่จดทะเบียนตอนนั้น
       หรือข่าวใหม่เกินกว่าจะมีราคาช่วงหลังครบ) จะ "ข้าม" แถวนั้นไปเลย ไม่เดา/เติมค่า
    4. ผลตอบแทนรายวันส่วนเกิน_t = ผลตอบแทน sector_t − ผลตอบแทน SPY_t  (t = t0+1 .. t0+21)
    5. คะแนนผลกระทบ = ผลรวมผลตอบแทนส่วนเกินราย วันตลอด 21 trading day หลังข่าว
       (คือ cumulative abnormal return / CAR แบบมาตรฐานของ event study — Brown & Warner 1985)
    6. แบ่ง 5 กลุ่มเท่ากันด้วย quantile -> label {-2,-1,0,1,2}
       *** bin edges คำนวณจาก TRAIN set เท่านั้น แล้วนำไปใช้กับ test ด้วย (กัน look-ahead
       bias จากการให้ขอบเขต quantile "เห็น" การกระจายของ test มาก่อน) ***

Train/test split: เรียงตามเวลา, test = ข่าวที่วันที่ >= (วันที่ล่าสุดในข้อมูล - 2 ปี)
                   ห้ามสุ่มแบ่ง (news วันเดียวกันไปกลุ่มเดียวกันทั้งหมดอยู่แล้วเพราะแบ่งด้วยวันที่)
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEWS_PATH = PROJECT_ROOT / "data" / "raw" / "macro_news_raw.parquet"
PRICE_CACHE_PATH = PROJECT_ROOT / "data" / "raw" / "sector_prices_raw.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "labels.parquet"

SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
BENCHMARK = "SPY"
ALL_TICKERS = SECTORS + [BENCHMARK]

PRE_WINDOW = 30    # trading days ก่อนข่าว ที่ต้องมีราคาครบ
POST_WINDOW_FETCH = 30   # trading days หลังข่าว ที่ต้องมีราคาครบ (ตามที่โจทย์ระบุ)
POST_WINDOW_LABEL = 21   # trading days หลังข่าว ที่ใช้คำนวณคะแนนผลกระทบจริง

N_QUANTILES = 5
QUANTILE_LABELS = [-2, -1, 0, 1, 2]

TEST_YEARS = 2

PRICE_START = "1996-01-01"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("s2_build_labels")


# --------------------------------------------------------------------------
# Step A: โหลด/ดาวน์โหลดราคา
# --------------------------------------------------------------------------

def load_prices():
    log.info(f"Downloading daily close prices for {ALL_TICKERS} from {PRICE_START} ...")
    raw = yf.download(
        ALL_TICKERS, start=PRICE_START, auto_adjust=True, progress=False, group_by="ticker"
    )
    if raw.empty:
        raise RuntimeError("yfinance returned no data — ตรวจสอบการเชื่อมต่อเครือข่าย")

    close = pd.DataFrame({t: raw[t]["Close"] for t in ALL_TICKERS if t in raw.columns.get_level_values(0)})
    close = close.sort_index()

    PRICE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    close.to_parquet(PRICE_CACHE_PATH)
    log.info(f"Saved raw price cache -> {PRICE_CACHE_PATH} ({close.shape[0]} trading days)")

    for t in ALL_TICKERS:
        n_valid = close[t].dropna().shape[0] if t in close.columns else 0
        if n_valid == 0:
            log.warning(f"[prices] {t}: NO DATA at all (ticker not returned by yfinance)")
        else:
            first = close[t].dropna().index.min().date()
            last = close[t].dropna().index.max().date()
            log.info(f"[prices] {t}: {n_valid} trading days, {first} -> {last}")

    return close


# --------------------------------------------------------------------------
# Step B: คำนวณคะแนนผลกระทบต่อข่าวแต่ละชิ้น x แต่ละ sector
# --------------------------------------------------------------------------

def build_scores(news_df, close):
    if BENCHMARK not in close.columns or close[BENCHMARK].dropna().empty:
        raise RuntimeError(f"ไม่มีข้อมูลราคาของ {BENCHMARK} เลย — ไม่สามารถสร้าง master trading calendar ได้")

    master_calendar = close[BENCHMARK].dropna().index  # DatetimeIndex, sorted
    n_cal = len(master_calendar)

    returns = close.pct_change()

    records = []
    skipped_no_t0 = 0
    skipped_window = {s: 0 for s in SECTORS}

    for _, news in news_df.iterrows():
        news_date = news["date"]

        pos = master_calendar.searchsorted(news_date)  # ตำแหน่ง trading day แรกที่ >= news_date
        if pos >= n_cal:
            skipped_no_t0 += 1
            continue
        idx0 = pos

        if idx0 - PRE_WINDOW < 0 or idx0 + POST_WINDOW_FETCH >= n_cal:
            # ไม่มี trading day พอในปฏิทิน master (SPY) เอง เช่น ข่าวใหม่เกินไป
            for s in SECTORS:
                skipped_window[s] += 1
            continue

        window_dates = master_calendar[idx0 - PRE_WINDOW: idx0 + POST_WINDOW_FETCH + 1]  # 61 วัน
        post_dates = master_calendar[idx0 + 1: idx0 + POST_WINDOW_LABEL + 1]             # 21 วันหลัง

        spy_window_ok = close.loc[window_dates, BENCHMARK].notna().all()
        if not spy_window_ok:
            for s in SECTORS:
                skipped_window[s] += 1
            continue

        spy_post_returns = returns.loc[post_dates, BENCHMARK]

        for sector in SECTORS:
            if sector not in close.columns:
                skipped_window[sector] += 1
                continue
            sector_window_ok = close.loc[window_dates, sector].notna().all()
            if not sector_window_ok:
                skipped_window[sector] += 1
                continue

            sector_post_returns = returns.loc[post_dates, sector]
            if sector_post_returns.isna().any() or spy_post_returns.isna().any():
                skipped_window[sector] += 1
                continue

            excess = sector_post_returns - spy_post_returns
            score = float(excess.sum())

            records.append({
                "date": news_date,
                "source": news["source"],
                "url": news["url"],
                "sector": sector,
                "score": score,
            })

    log.info(f"[labels] news skipped (no t0 in calendar): {skipped_no_t0}")
    for s, n in skipped_window.items():
        log.info(f"[labels] {s}: skipped {n} news-sector pairs (incomplete price window)")

    return pd.DataFrame.from_records(records)


# --------------------------------------------------------------------------
# Step C: train/test split (chronological) + quantile label (fit on train only)
# --------------------------------------------------------------------------

def split_and_label(df):
    df = df.sort_values(["date", "source", "sector"]).reset_index(drop=True)

    max_date = df["date"].max()
    cutoff = max_date - pd.DateOffset(years=TEST_YEARS)
    df["split"] = np.where(df["date"] >= cutoff, "test", "train")

    log.info(f"Train/test cutoff date: {cutoff.date()} (max date in data: {max_date.date()})")

    train_scores = df.loc[df["split"] == "train", "score"]
    if train_scores.nunique() < N_QUANTILES:
        raise RuntimeError("train set มีค่า score ไม่พอที่จะแบ่ง quantile ได้ 5 กลุ่ม")

    _, bin_edges = pd.qcut(train_scores, N_QUANTILES, labels=False, retbins=True, duplicates="drop")
    if len(bin_edges) - 1 != N_QUANTILES:
        raise RuntimeError(
            f"quantile ของ train แบ่งได้แค่ {len(bin_edges) - 1} กลุ่ม (ต้องการ {N_QUANTILES}) "
            f"— score อาจมีค่าซ้ำกันเยอะเกินไป"
        )

    # เปิดขอบนอกสุดเป็น +-inf กันกรณี test มีค่าหลุด range ของ train
    edges = bin_edges.copy()
    edges[0] = -np.inf
    edges[-1] = np.inf

    df["label"] = pd.cut(df["score"], bins=edges, labels=QUANTILE_LABELS, include_lowest=True)
    df["label"] = df["label"].astype(int)

    log.info("Quantile bin edges (fit on train only): " + ", ".join(f"{e:.5f}" for e in bin_edges))

    return df


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    if not NEWS_PATH.exists():
        raise FileNotFoundError(f"ไม่พบ {NEWS_PATH} — รัน s1_fetch_news.py ก่อน")

    news_df = pd.read_parquet(NEWS_PATH)
    log.info(f"Loaded {len(news_df)} news rows from {NEWS_PATH}")

    close = load_prices()

    scores_df = build_scores(news_df, close)
    if scores_df.empty:
        raise RuntimeError("ไม่มีแถวไหนผ่านเงื่อนไขข้อมูลราคาครบเลย — หยุด ไม่สร้างไฟล์ label")

    labels_df = split_and_label(scores_df)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    labels_df.to_parquet(OUT_PATH, index=False)

    # --------------------- รายงานผล ---------------------
    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)

    log.info("จำนวนข่าว (unique, จาก data/raw) แยกตามแหล่ง:")
    log.info("\n" + news_df["source"].value_counts().to_string())

    log.info(f"\nจำนวนแถวรวมใน labels.parquet: {len(labels_df)}  (1 แถว = 1 ข่าว x 1 sector)")

    log.info("\nสัดส่วนแต่ละ label (รวมทั้ง train+test):")
    log.info("\n" + (labels_df["label"].value_counts(normalize=True).sort_index() * 100).round(2).astype(str).add(" %").to_string())

    log.info("\nTrain vs Test:")
    log.info("\n" + labels_df["split"].value_counts().to_string())

    log.info("\nสัดส่วน label แยกตาม split:")
    log.info("\n" + (
        labels_df.groupby("split")["label"].value_counts(normalize=True).sort_index() * 100
    ).round(2).astype(str).add(" %").to_string())

    log.info(f"\nจำนวนแถวแยกตาม sector:")
    log.info("\n" + labels_df["sector"].value_counts().sort_index().to_string())

    log.info(f"\nช่วงวันที่ในไฟล์ label: {labels_df['date'].min().date()} -> {labels_df['date'].max().date()}")
    log.info(f"Saved to: {OUT_PATH}")

    return labels_df


if __name__ == "__main__":
    main()
