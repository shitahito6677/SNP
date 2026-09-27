"""
Adapter ของ Model A (กฎอันดับ 1–2 ใน LEADERBOARD) สำหรับ web test simulator — ตรง interface ของ sandbox/inference/model_a.py

    predict(ticker: str, date: str, rule: str = "rule1") -> dict
      คง key เดิม: class ("buy"|"hold"|"sell"), score ([0, 1]), is_stub (False)
      เพิ่ม key : score_0_100, signal, reasons (list), model_version, applicable, disclaimer, rule, rebalance_date

⚠️ ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด — ทั้งสองกฎอยู่ระดับ C (ไม่ผ่าน S3) และยังไม่ freeze
⚠️ ห้ามใช้ผลใน sandbox เลือกหรือปรับกฎ (AUTORUN/ผู้ใช้)
⚠️ held-out ยังล็อก: วันที่ ≥ 2023-06-30 คืน hold + applicable=False (ไม่มีคะแนน)

ไม่ต้อง import โค้ดวิจัย — อ่านคะแนนที่คำนวณไว้แล้วใน export/scores_rule*.csv (สร้างด้วย `python3 -m export.build_scores`)
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
IS_STUB = False
MODEL_VERSION = "experimental-not-frozen"
DISCLAIMER = "ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด"
HELDOUT_CUTOFF = pd.Timestamp("2023-06-30")
RULE_DESC = {
    "rule1": "กฎอันดับ 1 (r004_Q_LOWACC_overall_W_CAP): accruals ต่ำ — top 20% (ขั้นต่ำ 50) ของ S&P 500 ไม่รวมการเงิน, ถ่วงน้ำหนักตาม market cap, rebalance มิ.ย.",
    "rule2": "กฎอันดับ 2 (r004_C_SHYQMOM_overall_W_CAP): shareholder yield + quality + momentum — top 20% (ขั้นต่ำ 50), ถ่วงน้ำหนักตาม market cap, rebalance รายเดือน",
}
SELL_PCT = 0.20  # ต่ำกว่า percentile 20 ของ universe = sell (สัญญาณแสดงผลเท่านั้น; backtest เป็น long-only)


@lru_cache(maxsize=None)
def _load(rule: str):
    s = pd.read_csv(HERE / f"scores_{rule}.csv", parse_dates=["R", "fy_t_end"])
    na = pd.read_csv(HERE / f"not_applicable_{rule}.csv", parse_dates=["R"])
    return s, na


def _match(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    t = ticker.upper()
    return df[(df["cur_ticker"].astype(str).str.upper() == t) | (df["ticker"].astype(str).str.upper() == t)
              | (df["yahoo"].astype(str).str.upper() == t.replace(".", "-"))]


def _out(cls, pct, applicable, reasons, rule, R):
    score = 0.5 if pct is None else float(pct)
    return {"class": cls, "score": round(score, 4), "is_stub": IS_STUB, "score_0_100": None if pct is None else round(100 * float(pct), 1),
            "signal": cls, "reasons": [DISCLAIMER] + reasons, "model_version": MODEL_VERSION, "applicable": applicable,
            "disclaimer": DISCLAIMER, "rule": rule, "rebalance_date": None if R is None else str(pd.Timestamp(R).date())}


def predict(ticker: str, date: str, rule: str = "rule1") -> dict:
    d = pd.Timestamp(date)
    if rule not in RULE_DESC:
        raise ValueError(f"rule ต้องเป็น {list(RULE_DESC)}")
    if d >= HELDOUT_CUTOFF:
        return _out("hold", None, False, [f"วันที่ {d.date()} อยู่ในช่วง held-out (≥ {HELDOUT_CUTOFF.date()}) ที่ยังล็อก — กฎยังไม่ freeze จึงไม่มีคะแนน"],
                    rule, None)
    s, na = _load(rule)
    Rs = sorted(s["R"].unique())
    past = [R for R in Rs if R <= d]
    if not past:
        return _out("hold", None, False, [f"ไม่มีคะแนนก่อน {pd.Timestamp(Rs[0]).date()} ในไฟล์ export"], rule, None)
    R = past[-1]
    row = _match(s[s["R"] == R], ticker)
    if row.empty:
        n = _match(na[na["R"] == R], ticker)
        why = n["reason_not_applicable"].iloc[0] if len(n) else "ไม่อยู่ในสมาชิก S&P 500 ณ วัน rebalance หรือไม่มีข้อมูลสัญญาณ"
        return _out("hold", None, False, [RULE_DESC[rule], f"rebalance {pd.Timestamp(R).date()}: {why}"], rule, R)
    r = row.iloc[0]
    cls = "buy" if bool(r["selected"]) else ("sell" if r["pct"] <= SELL_PCT else "hold")
    reasons = [RULE_DESC[rule],
               f"rebalance {pd.Timestamp(R).date()}: อันดับ {int(r['rank'])}/{int(r['n_ranked'])} (percentile {100 * r['pct']:.1f}); "
               f"เลือก {int(r['n_selected'])} อันดับแรก → {'อยู่ในพอร์ต' if r['selected'] else 'ไม่อยู่ในพอร์ต'}"
               + (f", น้ำหนักตาม market cap {100 * r['cap_weight']:.2f}%" if pd.notna(r["cap_weight"]) else ""),
               f"งบที่ใช้: ปีบัญชีสิ้นสุด {pd.Timestamp(r['fy_t_end']).date() if pd.notna(r['fy_t_end']) else '?'} (point-in-time)"]
    if rule == "rule1":
        reasons.append(f"−accruals/สินทรัพย์เฉลี่ย = {r['value']:.4f} (สูง = กำไรเป็นเงินสดมากกว่า)")
    else:
        reasons.append(f"percentile รายเสา: shareholder yield {100 * r['p_shy']:.0f}, quality {100 * r['p_quality']:.0f}, "
                       f"momentum 12-1 {100 * r['p_mom']:.0f} → คะแนนรวม {100 * r['value']:.1f}")
    if cls == "sell":
        reasons.append(f"percentile ≤ {100 * SELL_PCT:.0f} → sell (สัญญาณแสดงผล; กฎจริงเป็น long-only)")
    return _out(cls, r["pct"], True, reasons, rule, R)
