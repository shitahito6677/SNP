"""
Export BMF20 (round 013) สำหรับ web simulator → model_A/export/bmf20-{funnel,weighted}/{manifest.json, signals.parquet}
รูปแบบเดียวกับ history export ของ sandbox v2 (manifest + signals: date, ticker, class, score, applicable, reasons, model_version, is_stub)

รัน (จาก model_A): python3 -m export.build_bmf20   (ต้องรัน rounds.round_013.run ก่อน — อ่าน scores.csv เท่านั้น ไม่คำนวณใหม่)
- ครอบคลุม rebalance มิ.ย. 2011 – มิ.ย. 2022 (ใช้ได้ถึง 30 มิ.ย. 2023) — held-out ยังล็อกตาม lib.guard
- ไม่ใช่การประเมินผล ไม่นับเป็น trial
"""
import json
from datetime import datetime, timezone

import pandas as pd

from lib import guard
from lib.paths import EXPORT, INTERIM, MODEL_A

MODEL_VERSION = "experimental-not-frozen"
DISCLAIMER = "ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด"
ROUND_DIR = MODEL_A / "rounds" / "round_013"
RULES = {
    "funnel": ("bmf20-funnel", "BMF20 funnel", "r013_BMF20_FUNNEL",
               "BMF20 คัดสองชั้น: BM 100 ตัวแรก → F-score 20 ตัว · เท่ากัน · รายปี",
               "percentile ของอันดับตามกฎ (100 ตัวแรกของ BM เรียงด้วย F-score ก่อน แล้วต่อด้วยตัวที่เหลือตามอันดับ BM) 0–100 มาก = ดี"),
    "weighted": ("bmf20-weighted", "BMF20 weighted", "r013_BMF20_WEIGHTED",
                 "BMF20 คะแนนรวม 0.6·BM + 0.4·F-score · 20 ตัว เท่ากัน · รายปี",
                 "คะแนนรวม = 0.6 × percentile BM + 0.4 × percentile F-score (0–100) มาก = ดี"),
}


def research_stats(tid: str) -> dict:
    r = pd.read_csv(ROUND_DIR / "results.csv").set_index("trial_id").loc[tid]
    keys = ("dec_sharpe", "dec_cagr", "dec_maxdd", "dec_sharpe_ew", "dec_sharpe_spy", "S1", "S2", "S6", "DSR", "S3")
    return {k: (float(r[k]) if isinstance(r[k], float) else str(r[k])) for k in keys}


def main():
    sc = pd.read_csv(ROUND_DIR / "scores.csv", parse_dates=["R", "fy_t_end"])
    panel = pd.read_parquet(INTERIM / "panel_annual.parquet")
    assert sc["R"].max() < guard.CUTOFF
    for rule, (version, short, tid, display, score_meaning) in RULES.items():
        rows = []
        for R, g in sc.groupby("R"):
            n = len(g)
            for r in g.sort_values(f"rank_{rule}").itertuples():
                rank = int(getattr(r, f"rank_{rule}"))
                sel = rank <= 20
                score = float(r.score_weighted) if rule == "weighted" else 100.0 * (n - rank + 1) / n
                head = (f"{short}: rebalance {R.date()} อันดับ {rank}/{n} → "
                        + ("selected (น้ำหนัก 5.00% เท่ากัน 20 ตัว)" if sel else "not selected"))
                detail = f"BM อันดับ {int(r.bm_rank)}/{n} (BM = {r.BM:.3f}), F-score {r.F:.2f}/9"
                if rule == "funnel":
                    detail += " · ผ่านชั้นแรก (BM 100 ตัวแรก)" if r.funnel_stage1 else " · ไม่ผ่านชั้นแรก (BM ไม่อยู่ใน 100 ตัวแรก)"
                else:
                    detail += f" · percentile BM {r.pBM:.1f}, F {r.pF:.1f} → คะแนน {r.score_weighted:.2f}"
                fy = f"งบปีสิ้นสุด {r.fy_t_end.date()} (point-in-time, first-filed)" if pd.notna(r.fy_t_end) else "งบปี ?"
                rows.append({"date": R, "ticker": r.yahoo, "class": "selected" if sel else "not_selected", "score": round(score, 3),
                             "applicable": True, "weight": 0.05 if sel else 0.0, "rank": rank, "n_ranked": n,
                             "BM": float(r.BM), "F": float(r.F), "reasons": [DISCLAIMER, head, detail, fy]})
            # สมาชิก S&P 500 ณ วัน R ที่ไม่อยู่ใน universe → not_applicable พร้อมเหตุผล
            ranked = set(g["yahoo"])
            for m in panel[panel["R"] == R].itertuples():
                y = m.yahoo if isinstance(m.yahoo, str) else None
                if y in ranked:
                    continue
                if m.financial:
                    why = "กลุ่มการเงิน (SIC 6000–6799) — กฎนี้ไม่ครอบคลุม"
                elif not m.in_U:
                    why = f"ไม่อยู่ใน universe (ราคา/market cap: {m.price_flag})"
                else:
                    why = "ไม่มี BM หรือ F-score (งบไม่ครบ ≥ 8/9 ข้อ)"
                rows.append({"date": R, "ticker": y or f"?{m.ticker}", "class": "not_applicable", "score": None, "applicable": False,
                             "weight": 0.0, "rank": None, "n_ranked": n, "BM": None, "F": None,
                             "reasons": [DISCLAIMER, f"{short}: rebalance {R.date()} — {why}"]})
        s = pd.DataFrame(rows).drop_duplicates(["date", "ticker"], keep="first")
        s["model_version"] = f"{MODEL_VERSION}:{tid}"
        s["is_stub"] = False
        s = s.sort_values(["date", "rank", "ticker"], na_position="last").reset_index(drop=True)
        d = EXPORT / version
        d.mkdir(exist_ok=True)
        s.to_parquet(d / "signals.parquet", index=False)
        sel = s[s["class"] == "selected"]
        assert (sel.groupby("date").size() == 20).all()
        man = {
            "model": "A", "version": version, "short_label": short, "display_name": display, "rule_id": tid,
            "model_version": MODEL_VERSION, "is_stub": False, "result_badge": "real",
            "signal_files": ["signals.parquet"], "key": "ticker",
            "coverage": {"start": str(s["date"].min().date()), "end": str(s["date"].max().date()),
                         "valid_through": str(guard.CUTOFF.date()), "n_rebalances": int(s["date"].nunique()),
                         "n_tickers": int(s["ticker"].nunique()), "avg_selected": float(sel.groupby("date").size().mean())},
            "rebalance": "annual_june",
            "classes": ["selected", "not_selected", "not_applicable"],
            "score_meaning": score_meaning,
            "source_experiment": f"model_A round 013 trial {tid} (rounds/round_013/run.py, trials.csv)",
            "research_stats": research_stats(tid),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notes": DISCLAIMER + " · ใช้ข้อมูลถึง 30 มิ.ย. 2023 เท่านั้น (held-out ล็อก) · backtest เดิมซื้อที่ close วัน R",
            "warnings": ["ระดับ C: ตก S1, S2, S3 และ S6 (ถือ 20 ตัว < 30)", "ยังไม่ freeze", DISCLAIMER,
                         "survivorship: universe มีเฉพาะหุ้นที่ Yahoo ยังมีราคา"],
        }
        (d / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
        print(version, "rows", len(s), "rebalances", man["coverage"]["n_rebalances"], man["coverage"]["start"], "→", man["coverage"]["end"],
              "selected/รอบ", man["coverage"]["avg_selected"], flush=True)
        # ตรวจ: ชุดหุ้นที่ selected ต้องตรงกับ picks_<rule>.csv ทุกรอบ
        pk = pd.read_csv(ROUND_DIR / f"picks_{rule}.csv", parse_dates=["R"])
        for R, g in pk.groupby("R"):
            assert set(g["ticker"]) == set(sel.loc[sel["date"] == R, "ticker"]), f"{version} {R.date()}: ไม่ตรงกับ picks"
        print(version, "ตรงกับ picks ทุกรอบ", flush=True)


if __name__ == "__main__":
    main()
