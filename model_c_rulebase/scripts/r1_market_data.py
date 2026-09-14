"""
r1_market_data.py — Phase R1: market data pipeline สำหรับ FOMC/Beige Book event study
(component ที่ 1 ของ Model C rule-based sector impact engine — ดูรายละเอียดสถาปัตยกรรม
เต็มใน experiments/log.md entry ของ exp_03 Phase R1)

ทฤษฎีที่ต้องใช้ market variable ชุดนี้:
    - Bernanke & Kuttner (2005, JF): ต้องแยก "surprise" ของนโยบายออกจากระดับดอกเบี้ยเอง
    - Gürkaynak, Sack & Swanson (2005): target factor (ดอกเบี้ยปัจจุบัน, ~DGS2 บนหน้าสั้น)
      กับ path factor (forward guidance, สะท้อนใน curve slope) ต้องแยกกัน ไม่ผสมเป็นตัวเดียว
    - Jarociński & Karadi (2020): ต้องมีทั้งฝั่ง rate (DGS2) และฝั่ง equity (SPY) วันเดียวกัน
      เพื่อแยก "policy shock" ออกจาก "information/Delphic shock" ด้วย sign restriction (ทำใน R2)

Input : data/processed/labels.parquet (จาก exp_01/exp_02 เดิม — ไม่แตะ ไม่สร้าง label ใหม่)
        ใช้แค่ (date, source, url) unique ของข่าว FOMC_statement/Beige_Book ที่มี CAR label
        แล้ว (452 ข่าว ณ ตอนเขียนสคริปต์นี้ — ตัวเลขจริงพิมพ์ตอนรัน ไม่ hardcode)
Output: model_c_rulebase/data/fomc_market_context.csv
        1 แถว = 1 ข่าว: date, source, url, t_prev, t0, rate_surprise, curve_slope_delta,
        dxy_delta, vix_delta, equity_move

Master trading calendar: ใช้ SPY calendar เดียวกับที่ src/s2_build_labels.py ใช้ตอนสร้าง CAR
(t0 = trading day แรกที่ >= วันข่าว, t_prev = trading day ก่อนหน้า t0 ใน calendar เดียวกัน)
เพื่อให้ equity_move กับ delta ของ FRED series ทุกตัวอ้างอิงช่วงเวลาเดียวกันเป๊ะกับที่ label
ถูกคำนวณไว้ (t0/t_prev ในไฟล์นี้ตรงกับ t0 ที่ s2_build_labels.py ใช้เป๊ะ)

กฎ "ห้ามเดา / ห้ามเติมค่ามั่ว":
    - rate_surprise (ΔDGS2) และ equity_move (SPY) เป็นตัวแปรบังคับสำหรับ shock classification
      ใน R2 — ถ้าหาไม่ได้ที่ t0 หรือ t_prev ข้ามทั้งแถว (log ไว้ ไม่เดา ไม่ประมาณ)
    - curve_slope_delta (ต้องการ DGS10) และ vix_delta (ต้องการ VIXCLS) มีข้อมูลย้อนหลังไกลกว่า
      ข่าวที่เก่าที่สุดในชุดนี้อยู่แล้ว (DGS10 ตั้งแต่ 1962, VIXCLS ตั้งแต่ 1990, ข่าวเริ่ม 1999)
      จึงคาดว่าครบทุกข่าว แต่ยังเช็คจริงและ log หากพลาด ไม่ถือเป็นค่าเริ่มต้น
    - dxy_delta (ต้องการ DTWEXBGS) มีข้อมูลย้อนหลังแค่ตั้งแต่ 2006-01-02 — ข่าวก่อนหน้านั้น
      (พบจริง 111/452 = 24.6% ของ label ที่มี ต่ำกว่า 2006) จะไม่มี dxy_delta จริง ๆ ตามข้อจำกัด
      ของแหล่งข้อมูล ไม่ใช่บั๊ก — เก็บเป็น NaN (ไม่ทิ้งทั้งแถวเพราะ dxy_delta ป้อนแค่ channel C5
      เดียวใน R4 ไม่ใช่ตัวตัดสิน shock_type หลัก) และรายงานจำนวนที่ขาดชัดเจนในสรุปผล

รัน (จาก project root): python3 -m model_c_rulebase.scripts.r1_market_data
"""

import logging
from pathlib import Path

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from fredapi import Fred

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LABELS_PATH = PROJECT_ROOT / "data" / "processed" / "labels.parquet"
OUT_PATH = PROJECT_ROOT / "model_c_rulebase" / "data" / "fomc_market_context.csv"

FRED_SERIES = {
    "DGS2": "DGS2",
    "DGS10": "DGS10",
    "DTWEXBGS": "DTWEXBGS",
    "VIXCLS": "VIXCLS",
}

BENCHMARK = "SPY"
PRICE_START = "1996-01-01"  # เหมือน s2_build_labels.py กันเคส SPY ยังไม่มีราคาช่วงต้น

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("r1_market_data")


def load_news_dates():
    labels = pd.read_parquet(LABELS_PATH)
    news = labels[["date", "source", "url"]].drop_duplicates().sort_values("date").reset_index(drop=True)
    news["date"] = pd.to_datetime(news["date"])
    return news


def fetch_fred_series():
    load_dotenv(PROJECT_ROOT / ".env")
    import os

    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise SystemExit("ไม่พบ FRED_API_KEY ใน .env")
    fred = Fred(api_key=api_key)

    series = {}
    for name, code in FRED_SERIES.items():
        s = fred.get_series(code).dropna()
        s.index = pd.to_datetime(s.index)
        series[name] = s
        log.info(f"[FRED] {name} ({code}): {len(s)} จุดข้อมูล, {s.index.min().date()} -> {s.index.max().date()}")
    return series


def fetch_spy():
    raw = yf.download(BENCHMARK, start=PRICE_START, auto_adjust=True, progress=False)
    close = raw["Close"][BENCHMARK].dropna()
    close.index = pd.to_datetime(close.index)
    log.info(f"[SPY] {len(close)} trading days, {close.index.min().date()} -> {close.index.max().date()}")
    return close


def calendar_lookup(series: pd.Series, news_date: pd.Timestamp):
    """คืน (t_prev, t0, value_prev, value_t0) โดย t0 = trading day แรกใน series.index
    ที่ >= news_date, t_prev = จุดก่อนหน้า t0 ใน calendar ของ series นั้นเอง
    คืน (None, None, None, None) ถ้าหาไม่ได้ (news_date เกิน range ของ series หรืออยู่ต้น series
    จนไม่มี t_prev)"""
    idx = series.index
    pos = idx.searchsorted(news_date)
    if pos >= len(idx) or pos == 0:
        return None, None, None, None
    t0 = idx[pos]
    t_prev = idx[pos - 1]
    return t_prev, t0, series.loc[t_prev], series.loc[t0]


def build_context(news: pd.DataFrame, fred_series: dict, spy: pd.Series):
    rows = []
    skipped_core = []  # ข่าวที่ขาด rate_surprise หรือ equity_move -> ข้ามทั้งแถว
    missing_dxy = 0
    missing_curve_or_vix = []

    for _, r in news.iterrows():
        news_date = r["date"]

        tp_dgs2, t0_dgs2, v_prev_dgs2, v_t0_dgs2 = calendar_lookup(fred_series["DGS2"], news_date)
        tp_spy, t0_spy, v_prev_spy, v_t0_spy = calendar_lookup(spy, news_date)

        if t0_dgs2 is None or t0_spy is None:
            skipped_core.append({"date": news_date, "source": r["source"], "url": r["url"],
                                  "reason": "หา t0/t_prev ของ DGS2 หรือ SPY ไม่ได้ (นอก range)"})
            continue

        rate_surprise = v_t0_dgs2 - v_prev_dgs2
        equity_move = (v_t0_spy / v_prev_spy) - 1.0

        # DGS10 สำหรับ curve slope — ใช้ t0/t_prev เดียวกับ DGS2 (จุดเดียวกันบน calendar ของ
        # bond market จึงตรงกันแทบทุกครั้ง เพราะ DGS2/DGS10 มาจาก series แหล่งเดียวกัน)
        tp_dgs10, t0_dgs10, v_prev_dgs10, v_t0_dgs10 = calendar_lookup(fred_series["DGS10"], news_date)
        if t0_dgs10 is not None and t0_dgs10 == t0_dgs2 and tp_dgs10 == tp_dgs2:
            curve_prev = v_prev_dgs10 - v_prev_dgs2
            curve_t0 = v_t0_dgs10 - v_t0_dgs2
            curve_slope_delta = curve_t0 - curve_prev
        else:
            curve_slope_delta = None
            missing_curve_or_vix.append((news_date, "curve_slope_delta"))

        tp_vix, t0_vix, v_prev_vix, v_t0_vix = calendar_lookup(fred_series["VIXCLS"], news_date)
        if t0_vix is not None:
            vix_delta = v_t0_vix - v_prev_vix
        else:
            vix_delta = None
            missing_curve_or_vix.append((news_date, "vix_delta"))

        tp_dxy, t0_dxy, v_prev_dxy, v_t0_dxy = calendar_lookup(fred_series["DTWEXBGS"], news_date)
        if t0_dxy is not None:
            dxy_delta = v_t0_dxy - v_prev_dxy
        else:
            dxy_delta = None
            missing_dxy += 1

        rows.append({
            "date": news_date.date().isoformat(),
            "source": r["source"],
            "url": r["url"],
            "t_prev": tp_dgs2.date().isoformat(),
            "t0": t0_dgs2.date().isoformat(),
            "rate_surprise": rate_surprise,
            "equity_move": equity_move,
            "curve_slope_delta": curve_slope_delta,
            "vix_delta": vix_delta,
            "dxy_delta": dxy_delta,
        })

    return pd.DataFrame(rows), skipped_core, missing_dxy, missing_curve_or_vix


def main():
    news = load_news_dates()
    log.info(f"Loaded {len(news)} unique FOMC/Beige Book news (from labels.parquet) ที่มี CAR label แล้ว")

    fred_series = fetch_fred_series()
    spy = fetch_spy()

    ctx, skipped_core, missing_dxy, missing_curve_or_vix = build_context(news, fred_series, spy)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ctx.to_csv(OUT_PATH, index=False)

    log.info("=" * 60)
    log.info("SUMMARY — Phase R1")
    log.info("=" * 60)
    log.info(f"ข่าวทั้งหมด: {len(news)}")
    log.info(f"ข่าวที่มี market context ครบ (rate_surprise + equity_move): {len(ctx)}")
    log.info(f"ข่าวที่ข้ามไป (ไม่มี t0/t_prev ของ DGS2 หรือ SPY — บังคับ ห้ามเดา): {len(skipped_core)}")
    for s in skipped_core:
        log.warning(f"  ข้าม: {s['date'].date()} ({s['source']}) — {s['reason']}")
    log.info(f"ข่าวที่ไม่มี dxy_delta (ก่อน DTWEXBGS เริ่มมีข้อมูล 2006-01-02): {missing_dxy}")
    if missing_curve_or_vix:
        log.warning(f"ข่าวที่ไม่มี curve_slope_delta/vix_delta ผิดคาด (ควรครบ): {len(missing_curve_or_vix)}")
        for d, field in missing_curve_or_vix:
            log.warning(f"  {d.date()}: missing {field}")
    else:
        log.info("curve_slope_delta และ vix_delta ครบทุกข่าวที่ผ่านเงื่อนไข core (ตามคาด)")
    log.info(f"Saved -> {OUT_PATH}")

    return ctx


if __name__ == "__main__":
    main()
