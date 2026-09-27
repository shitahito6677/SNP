"""
แปลงผล rule engine ของ exp_03 (R4 `sector_impact_score` รายข่าว × sector) เป็น signal contract ของ sandbox v2
→ model_c_rulebase/export/rulebase-exp03/{manifest.json, signals.parquet}

รัน (จาก repo root): python3 -m model_c_rulebase.export.build_export

- เรียก `scripts/r5b_validate.run_engine_on_all_news()` เดิม (อ่าน R1+R2 market context + R3 structured vars ที่สกัดไว้แล้ว)
  **ไม่เรียก Qwen/LLM** และไม่แก้ไฟล์ใด ๆ ของ exp_03
- class: `score > +NEUTRAL_BAND` = positive, `< −NEUTRAL_BAND` = negative, อื่น ๆ = neutral
  (NEUTRAL_BAND เป็นค่าแสดงผลที่ตั้งเอง ไม่ได้ tune กับผลตอบแทน — condition ใช้ `score` ดิบเองได้)
- ⚠️ ผล R5: 0/216 cells ผ่าน |rho| > 0.3 → negative result — ติด badge "negative" เสมอ
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from model_c_rulebase.engine.sector_rules import CHANNEL_NAMES, SECTORS
from model_c_rulebase.scripts import r5b_validate as r5

OUT = Path(__file__).resolve().parent / "rulebase-exp03"
NEUTRAL_BAND = 0.10
SOURCE_LABEL = {"FOMC_statement": "FOMC statement", "Beige_Book": "Beige Book"}


def main():
    logging.disable(logging.INFO)
    s = r5.run_engine_on_all_news()
    s = r5.assign_time_split(s)
    test_start = s.loc[s["r5_split"] == "test", "date"].min()
    s["class"] = "neutral"
    s.loc[s["score"] > NEUTRAL_BAND, "class"] = "positive"
    s.loc[s["score"] < -NEUTRAL_BAND, "class"] = "negative"
    s["reasons"] = [
        [f"C rulebase-exp03: {SOURCE_LABEL.get(r.source, r.source)} {r.date} · shock {r.shock_type} → "
         f"{r.sector} sector_impact_score {r.score:+.3f} ({r['class']})",
         "exp_03 R5: 0/216 cells ผ่าน |rho|>0.3 (negative result)"]
        + (["low_confidence (dampener ×0.5)"] if r.low_confidence else [])
        + (["อยู่ใน test set ของ exp_03 (R5 ไม่ได้ประเมินช่วงนี้)"] if r.r5_split == "test" else [])
        for _, r in s.iterrows()
    ]
    out = pd.DataFrame({
        "date": pd.to_datetime(s["date"]), "sector": s["sector"], "class": s["class"], "score": s["score"].round(6),
        "applicable": True, "reasons": s["reasons"], "model_version": "rulebase-exp03", "is_stub": False,
        "source": s["source"], "shock_type": s["shock_type"], "low_confidence": s["low_confidence"].astype(bool),
        "url": s["url"], "exp03_split": s["r5_split"],
    })
    # หลายข่าววันเดียวกัน (พบจริง 2 วัน) → เก็บแถวแรกตามลำดับ engine (ไม่เฉลี่ย เพื่อให้ reasons ตรงกับข่าวเดียว)
    dup = out.duplicated(["date", "sector"], keep=False)
    if dup.any():
        print("⚠️ ข่าวซ้ำวันเดียวกัน", int(dup.sum()), "แถว — เก็บแถวแรก (ตามลำดับ engine)")
        out = out.drop_duplicates(["date", "sector"], keep="first")
    out = out.sort_values(["date", "sector"]).reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT / "signals.parquet", index=False)
    m = {
        "model": "C", "version": "rulebase-exp03", "short_label": "C-rb03",
        "display_name": "Rule-based sector impact (exp_03) — FOMC/Beige Book",
        "rule_id": "exp_03 R4 sector_rules.score_event", "is_stub": False, "result_badge": "negative",
        "signal_files": ["signals.parquet"], "key": "sector",
        "coverage": {"start": str(out["date"].min().date()), "end": str(out["date"].max().date()),
                     "n_events": int(out["date"].nunique()), "n_sectors": int(out["sector"].nunique()),
                     "sectors": SECTORS},
        "rebalance": "event",
        "asof": {"max_age_days": 60},
        "classes": ["positive", "neutral", "negative"],
        "score_meaning": f"sector_impact_score ดิบจาก engine (ไม่มีหน่วย, ช่วงจริง {out['score'].min():.2f}…{out['score'].max():.2f}); "
                         f"|score| ≤ {NEUTRAL_BAND} = neutral (ค่าแสดงผล ไม่ได้ tune)",
        "channels": CHANNEL_NAMES,
        "source_experiment": "exp_03 rule-based sector impact engine (PR #1, model_c_rulebase/)",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes": "exp_03: 0/216 cells ผ่าน |rho|>0.3 — negative result; ใช้เพื่อทดสอบระบบเท่านั้น",
        "warnings": [
            "NEGATIVE RESULT: exp_03 R5 0/216 cells ผ่าน |rho|>0.3",
            f"เหตุการณ์ตั้งแต่ {test_start} อยู่ใน test set ของ exp_03 (ช่วง sandbox 2021+ อยู่ในนี้ทั้งหมด)",
            "vix_p90 ของ VIX amplifier คำนวณจากทั้งช่วง 1999–2026 (look-ahead เล็กน้อยใน engine เดิม)",
            "ข่าวออกระหว่างวัน (~14:00 ET) → ใช้ได้ ณ close วันข่าว, execute วันถัดไป",
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
    print(f"rulebase-exp03: {len(out)} แถว, {m['coverage']['n_events']} ข่าว {m['coverage']['start']} → {m['coverage']['end']}; "
          f"class {out['class'].value_counts().to_dict()}; test set เริ่ม {test_start}")


if __name__ == "__main__":
    main()
