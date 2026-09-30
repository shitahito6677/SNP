"""
คำนวณคะแนนล่วงหน้าของกฎอันดับ 1–2 ใน LEADERBOARD สำหรับ web simulator (sandbox) — ไม่ใช่การประเมินผล ไม่นับเป็น trial
รัน (จาก model_A): python3 -m export.build_scores

⚠️ ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด — กฎยังไม่ผ่านเกณฑ์ (ระดับ C) และยังไม่ freeze
⚠️ held-out ยังล็อก: คำนวณได้เฉพาะ rebalance ก่อน 2023-06-30 (lib.guard) — วันหลังจากนั้น adapter จะคืน hold/applicable=False
"""
import pandas as pd

from lib import cik_map, audit, panel, strategy as st
from lib.paths import EXPORT
from rounds.round_002.run import composite
from rounds.round_003.run import Q, monthly_universe
from rounds.round_004.run import build as build_r004

MODEL_VERSION = "experimental-not-frozen"
DISCLAIMER = "ทดลองระบบ ข้อมูลไม่ครบ ไม่ใช่หลักฐานว่ากฎชนะตลาด"
START = pd.Timestamp("2021-06-01")  # sandbox ใช้ราคาตั้งแต่ 2021-09 → rebalance ล่าสุดก่อนหน้าคือ มิ.ย. 2021
RULES = {
    "rule1": {"trial_id": "r004_Q_LOWACC_overall_W_CAP", "freq": "A",
              "desc": "accruals ต่ำ (Sloan 1996): เลือก top 20% (ขั้นต่ำ 50) ของ −(กำไรสุทธิ − กระแสเงินสดจากการดำเนินงาน)/สินทรัพย์เฉลี่ย, ถ่วงน้ำหนักตาม market cap, rebalance มิ.ย."},
    "rule2": {"trial_id": "r004_C_SHYQMOM_overall_W_CAP", "freq": "M",
              "desc": "shareholder yield + quality + momentum 12-1 (percentile เฉลี่ยเท่ากัน 3 เสา): เลือก top 20% (ขั้นต่ำ 50), ถ่วงน้ำหนักตาม market cap, rebalance รายเดือน"},
}


def _scores(u: pd.DataFrame, col: str, extra: list) -> pd.DataFrame:
    out = []
    for R, g in u.groupby("R"):
        g = g[g[col].notna()].drop_duplicates("yahoo").sort_values([col, "yahoo"], ascending=[False, True]).copy()
        n = min(len(g), max(50, int(round(0.2 * len(g)))))
        g["rank"] = range(1, len(g) + 1)
        g["n_ranked"] = len(g)
        g["n_selected"] = n
        g["selected"] = g["rank"] <= n
        g["pct"] = g[col].rank(pct=True)
        sel = g[g["selected"]]
        g["cap_weight"] = (g["mcap"] / sel["mcap"].sum()).where(g["selected"])
        out.append(g[["R", "cik", "ticker", "yahoo", "sic_group", "fy_t_end", "mcap", col, "pct", "rank", "n_ranked", "n_selected",
                      "selected", "cap_weight"] + extra])
    return pd.concat(out, ignore_index=True).rename(columns={col: "value"})


def main():
    ctx = panel.Ctx()
    inv = {}
    for tk, c in cik_map.load_current_map().items():
        inv.setdefault(c, []).append(tk)
    cur_ticker = {c: audit.common_ticker(v) for c, v in inv.items()}
    dfm, um = monthly_universe(ctx)
    # rule 1 — annual
    dfa = panel.build(panel.rebalance_dates(ctx, "A"), ctx, "annual")
    ua = dfa[dfa["in_U"]].drop_duplicates(["R", "yahoo"])
    s1 = _scores(ua, "Q_LOWACC", [])
    # rule 2 — monthly composite (สูตรเดียวกับ round 003/004)
    parts = []
    for R, g in um.groupby("R"):
        g = g.copy()
        g["_c"] = composite(g, [["A_SHY"], Q, ["C_MOM"]], False)
        for name, cols in (("p_shy", ["A_SHY"]), ("p_quality", Q), ("p_mom", ["C_MOM"])):
            g[name] = composite(g, [cols], False)
        parts.append(g)
    s2 = _scores(pd.concat(parts), "_c", ["p_shy", "p_quality", "p_mom", "A_SHY", "C_MOM", "Q_GPA", "Q_ROIC", "Q_LOWACC"])
    # ตรวจว่าชุดหุ้นที่เลือกตรงกับ backtest ของ round 004 (W_CAP) ทุกรอบ
    for rule, s, freq, base in (("rule1", s1, "A", "r001_Q_LOWACC_overall"), ("rule2", s2, "M", "r003_C_SHYQMOM_overall")):
        dates = panel.rebalance_dates(ctx, freq)
        h = build_r004(um[um["R"].isin(dates)], base, "W_CAP", dates)
        for R, w in h.items():
            got = set(s[(s["R"] == R) & s["selected"]]["yahoo"])
            assert got == set(w), f"{rule} {R.date()}: ชุดหุ้นไม่ตรงกับ backtest"
        print(rule, "selection matches round 004 backtest for", len(h), "rebalances")
    # สมาชิกที่ไม่อยู่ใน U (เช่น กลุ่มการเงิน) — เพื่อให้ adapter ตอบ applicable=False พร้อมเหตุผล
    for rule, s, src in (("rule1", s1, dfa), ("rule2", s2, dfm)):
        s = s[s["R"] >= START].copy()
        s["cur_ticker"] = s["cik"].map(cur_ticker)
        na = src[(src["R"] >= START) & ~src["in_U"].fillna(False).astype(bool)][["R", "cik", "ticker", "yahoo", "financial", "price_flag"]].copy()
        na["cur_ticker"] = na["cik"].map(cur_ticker)
        na["reason_not_applicable"] = na.apply(lambda r: "กลุ่มการเงิน (SIC 6000–6799) — กฎนี้ไม่ครอบคลุม" if r["financial"] else
                                               f"ไม่อยู่ใน universe (ข้อมูลราคา/market cap: {r['price_flag']})", axis=1)
        s.to_csv(EXPORT / f"scores_{rule}.csv", index=False)
        na.drop(columns=["financial"]).to_csv(EXPORT / f"not_applicable_{rule}.csv", index=False)
        print(rule, "rows", len(s), "rebalances", s["R"].nunique(), s["R"].min().date(), "→", s["R"].max().date(), "| not applicable rows", len(na))


if __name__ == "__main__":
    main()
