"""
สร้าง signal ของ Model A **ทุกรอบ rebalance ย้อนหลัง** (2011-06 → ก่อน held-out) สำหรับ sandbox v2 — 5 กฎตาม
DATA_CONTRACT.md ข้อ 6 → model_A/export/<version>/{manifest.json, signals.parquet}

รัน (จาก model_A): python3 -m export.build_history

- เรียก `rounds.round_004.run.build()` เดิมเพื่อเลือกหุ้น/น้ำหนัก (ไม่ re-implement logic) และ `ranked()` เดิมเพื่อจัดอันดับ
- ตรวจว่า A2 (W_CAP) และ A5 เลือกหุ้นตรงกับ export เดิม (scores_rule1/2.csv) ทุกรอบที่ซ้อนกัน
- held-out ยังล็อกตาม lib.guard (rebalance < 2023-06-30) — ไม่ได้ตั้ง FINAL_EVAL
- ไม่ใช่การประเมินผล ไม่นับเป็น trial (อ่านอย่างเดียวจาก panel ที่ cache ไว้)
"""
import json
from datetime import datetime, timezone

import pandas as pd

from lib import guard, panel
from lib.paths import EXPORT, MODEL_A
from rounds.round_003.run import monthly_universe
from rounds.round_004.run import build, ranked

MODEL_VERSION = "experimental-not-frozen"
DISCLAIMER = "ทดลองระบบ — กฎยังไม่ผ่าน S3 (DSR) และยังไม่ freeze ไม่ใช่หลักฐานว่ากฎชนะตลาด"

RULES = [
    # label, trial_id, base, variant, freq, display, weight desc
    ("A1", "r001_Q_LOWACC_overall", "r001_Q_LOWACC_overall", "EW", "A",
     "Low accruals · EW · รายปี (กฎหลัก)", "เท่ากัน"),
    ("A2", "r004_Q_LOWACC_overall_W_CAP", "r001_Q_LOWACC_overall", "W_CAP", "A",
     "Low accruals · ถ่วง market cap · รายปี", "market cap ณ วัน rebalance"),
    ("A3", "r004_Q_LOWACC_overall_BUFFER", "r001_Q_LOWACC_overall", "BUFFER", "A",
     "Low accruals · buffer top 30% · รายปี", "เท่ากัน"),
    ("A4", "r004_Q_LOWACC_overall_W_IV", "r001_Q_LOWACC_overall", "W_IV", "A",
     "Low accruals · inverse-vol · รายปี", "1/vol 252 วัน"),
    ("A5", "r004_C_SHYQMOM_overall_W_CAP", "r003_C_SHYQMOM_overall", "W_CAP", "M",
     "SHY + Quality + Momentum · ถ่วง market cap · รายเดือน", "market cap ณ วัน rebalance"),
]
VALUE_DESC = {"r001_Q_LOWACC_overall": "−accruals/สินทรัพย์เฉลี่ย", "r003_C_SHYQMOM_overall": "composite SHY+Q+MOM"}


def trial_stats(trial_id: str) -> dict:
    t = pd.read_csv(MODEL_A / "trials.csv")
    r = t[t["trial_id"] == trial_id]
    out = {}
    if len(r):
        r = r.iloc[-1]
        out = {k: (None if pd.isna(r[k]) else (bool(r[k]) if isinstance(r[k], (bool,)) else r[k]))
               for k in ("dec_sharpe", "dec_cagr", "dec_maxdd", "dec_sharpe_ew", "dec_sharpe_spy", "S1", "S2", "S6")}
        out = {k: (float(v) if isinstance(v, float) else (str(v) if v is not None else None)) for k, v in out.items()}
    rnd = trial_id[1:4]
    p = MODEL_A / "rounds" / f"round_{rnd}" / "results.csv"
    if p.exists():
        rr = pd.read_csv(p)
        rr = rr[rr["trial_id"] == trial_id]
        if len(rr) and "DSR" in rr:
            out["DSR"] = float(rr["DSR"].iloc[0])
            out["S3"] = str(rr["S3"].iloc[0])
    return out


def main():
    ctx = panel.Ctx()
    dfm, um = monthly_universe(ctx)
    manifests = []
    for label, trial_id, base, variant, freq, display, wdesc in RULES:
        dates = panel.rebalance_dates(ctx, freq)
        u = um[um["R"].isin(dates)]
        hold = build(u, base, variant, dates)
        rows = []
        for R in dates:
            g = ranked(u[u["R"] == R], base)
            n_ranked = len(g)
            pct = g["_v"].rank(pct=True)
            h = hold[R]
            w = ({y: 1.0 / len(h) for y in h} if isinstance(h, list)
                 else {y: v / sum(h.values()) for y, v in h.items()})
            for rank, (idx, r) in enumerate(g.iterrows(), start=1):
                sel = r["yahoo"] in w
                p = float(pct.loc[idx])
                reasons = [
                    f"{label} {trial_id}: rebalance {R.date()} อันดับ {rank}/{n_ranked} (percentile {100 * p:.1f}) → "
                    + (f"selected, น้ำหนัก {100 * w[r['yahoo']]:.2f}% ({wdesc})" if sel else "not selected"),
                    f"{VALUE_DESC[base]} = {r['_v']:.4f}",
                    f"งบปีสิ้นสุด {pd.Timestamp(r['fy_t_end']).date() if pd.notna(r['fy_t_end']) else '?'} (point-in-time, first-filed)",
                ]
                if variant == "BUFFER" and sel and rank > len(w):
                    reasons.append("ถือต่อจากรอบก่อน (ยังอยู่ใน top 30%)")
                rows.append({"date": R, "ticker": r["yahoo"], "class": "selected" if sel else "not_selected",
                             "score": round(100 * p, 3), "applicable": True, "weight": w.get(r["yahoo"], 0.0),
                             "rank": rank, "n_ranked": n_ranked, "value": float(r["_v"]), "reasons": reasons})
            # สมาชิก S&P 500 ณ วัน R ที่ไม่อยู่ใน universe / ไม่มีค่าสัญญาณ → applicable=False พร้อมเหตุผล
            members = dfm[dfm["R"] == R]
            ranked_set = set(g["yahoo"])
            for r in members.itertuples():
                y = r.yahoo if isinstance(r.yahoo, str) else None
                key = y or f"?{r.ticker}"
                if y in ranked_set:
                    continue
                if r.financial:
                    why = "กลุ่มการเงิน (SIC 6000–6799) — กฎนี้ไม่ครอบคลุม"
                elif not r.in_U:
                    why = f"ไม่อยู่ใน universe (ราคา/market cap: {r.price_flag})"
                else:
                    why = "ไม่มีค่าสัญญาณ (งบ/ราคาไม่ครบ)"
                rows.append({"date": R, "ticker": key, "class": "not_applicable", "score": None, "applicable": False,
                             "weight": 0.0, "rank": None, "n_ranked": n_ranked, "value": None,
                             "reasons": [f"{label} {trial_id}: rebalance {R.date()} — {why}"]})
        s = pd.DataFrame(rows).drop_duplicates(["date", "ticker"], keep="first")
        s["model_version"] = f"{MODEL_VERSION}:{trial_id}"
        s["is_stub"] = False
        s["date"] = pd.to_datetime(s["date"])
        s = s.sort_values(["date", "rank", "ticker"], na_position="last").reset_index(drop=True)
        d = EXPORT / f"{label}_{trial_id}"
        d.mkdir(exist_ok=True)
        s.to_parquet(d / "signals.parquet", index=False)
        sel = s[s["class"] == "selected"]
        m = {
            "model": "A", "version": f"{label}_{trial_id}", "short_label": label, "display_name": display,
            "rule_id": trial_id, "is_stub": False, "result_badge": "real",
            "signal_files": ["signals.parquet"], "key": "ticker",
            "coverage": {"start": str(s["date"].min().date()), "end": str(s["date"].max().date()),
                         "valid_through": str(guard.CUTOFF.date()), "n_rebalances": int(s["date"].nunique()),
                         "n_tickers": int(s["ticker"].nunique()),
                         "avg_selected": round(float(sel.groupby("date").size().mean()), 1)},
            "rebalance": "annual_june" if freq == "A" else "monthly",
            "classes": ["selected", "not_selected", "not_applicable"],
            "score_meaning": "percentile 0–100 ของสัญญาณภายใน universe วันนั้น (มาก = ดี)",
            "source_experiment": f"model_A AUTORUN trial {trial_id} (rounds/round_{trial_id[1:4]}/run.py, trials.csv)",
            "research_stats": trial_stats(trial_id),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notes": DISCLAIMER + " · ranking เป็น cross-sectional ทั้ง universe — อ่านจากไฟล์นี้เท่านั้น ห้ามคำนวณใหม่จาก subset"
                     + " · backtest เดิมซื้อที่ close วัน R (sandbox ใช้ R+1)",
            "warnings": ["ไม่ผ่าน S3 (DSR < 0.95) — ระดับ C", "ยังไม่ freeze", "universe ไม่มีหุ้นที่ Yahoo ไม่มีราคา (survivorship บางส่วน)"],
        }
        (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
        manifests.append(m)
        print(label, trial_id, "rows", len(s), "rebalances", m["coverage"]["n_rebalances"],
              m["coverage"]["start"], "→", m["coverage"]["end"], "avg selected", m["coverage"]["avg_selected"], flush=True)

    # ตรวจกับ export เดิม: ชุดหุ้นที่เลือก + น้ำหนัก cap ต้องตรงกันทุกรอบที่ซ้อนกัน
    for label, rule in (("A2", "rule1"), ("A5", "rule2")):
        old = pd.read_csv(EXPORT / f"scores_{rule}.csv", parse_dates=["R"])
        new = pd.read_parquet(EXPORT / [f"{m['version']}" for m in manifests if m["short_label"] == label][0] / "signals.parquet")
        for R, g in old.groupby("R"):
            a = set(g.loc[g["selected"], "yahoo"])
            nb = new[(new["date"] == R) & (new["class"] == "selected")]
            assert a == set(nb["ticker"]), f"{label} {R.date()}: ชุดหุ้นไม่ตรงกับ scores_{rule}.csv"
            ow = g.loc[g["selected"]].set_index("yahoo")["cap_weight"]
            nw = nb.set_index("ticker")["weight"]
            assert (ow - nw.reindex(ow.index)).abs().max() < 1e-9, f"{label} {R.date()}: น้ำหนักไม่ตรง"
        print(label, "ตรงกับ", f"scores_{rule}.csv", "ทุกรอบ:", old["R"].nunique(), "รอบ")

    # ตรวจกับ NAV ของ backtest เดิม: backtest engine ของ Model A บน holdings จาก signals ต้องได้ NAV เดิมเป๊ะ
    from lib import backtest as bt, prices
    from lib.paths import INTERIM
    adj = guard.clip(prices.load_adj_close())
    navs = {**pd.read_parquet(INTERIM / "r001_nav.parquet").to_dict("series"),
            **pd.read_parquet(INTERIM / "r004_nav.parquet").to_dict("series")}
    for m in manifests:
        s = pd.read_parquet(EXPORT / m["version"] / "signals.parquet")
        sel = s[s["class"] == "selected"]
        hold = {R: dict(zip(g["ticker"], g["weight"])) for R, g in sel.groupby("date")}
        nav = bt.run(hold, adj, guard.CUTOFF, cost=0.001)["nav"]
        ref = navs[m["rule_id"]].dropna()
        err = float((nav.reindex(ref.index) / ref - 1).abs().max())
        assert err < 1e-9, f"{m['short_label']}: NAV ไม่ตรงกับ backtest เดิม (max rel diff {err:.2e})"
        print(m["short_label"], "NAV ตรงกับ backtest เดิม (max rel diff", f"{err:.1e})")


if __name__ == "__main__":
    main()
