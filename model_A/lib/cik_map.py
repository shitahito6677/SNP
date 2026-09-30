"""
จับคู่ ticker (ณ ช่วงเวลาที่อยู่ใน S&P 500) → SEC CIK แบบรู้เวลา

อุปมา: ticker เหมือน "เลขที่บ้าน" ที่เปลี่ยนเจ้าของได้ ส่วน CIK เหมือน "เลขบัตรประชาชน" ของบริษัทที่ไม่เปลี่ยน
เราจึงต้องถามว่า "ช่วงเวลานั้น ใครอยู่บ้านเลขที่นี้" ไม่ใช่ "ตอนนี้ใครอยู่"

ขั้นตอน (build → build_segments → apply_overrides):
  1. build: สรุปต่อ spell ด้วยวิธีเดิม (majority ของ prefix) + flag conflict กับ SEC ticker ปัจจุบัน — ใช้เป็น diagnostic
  2. build_segments: แตก spell เป็นรายปี
       ผู้สมัคร (candidates) = CIK ที่ prefix ของไฟล์ XBRL ตรงกับ ticker ในช่วง spell
                               + CIK จาก SEC ticker ปัจจุบัน (ถ้ายื่นงบในช่วงนั้นจริง)
       ปี Y เลือกผู้สมัครที่ยื่น 10-K ในปี Y (ดูจาก companyfacts) ที่มีหลักฐาน prefix มากที่สุดทั้ง spell
       (เสมอกัน → total assets ใหญ่กว่า = บริษัทแม่ ไม่ใช่บริษัทลูก/บริษัทเล็กที่ใช้ prefix ซ้ำ)
       เปลี่ยน CIK ณ วันที่ 10-K แรกของ CIK ใหม่ในปีนั้น (point-in-time)
  3. apply_overrides: กรณีที่กฎทั่วไปตัดสินไม่ได้ ใช้ lib/cik_overrides.csv (มีหลักฐานจาก SEC submissions ทุกแถว)
"""

import json

import pandas as pd
import requests

from lib.paths import SEC_DIR, SEC_USER_AGENT

CURRENT_MAP = SEC_DIR / "company_tickers.json"
PERIODIC = {"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT"}


def load_current_map() -> dict:
    if not CURRENT_MAP.exists():
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": SEC_USER_AGENT}, timeout=60)
        r.raise_for_status()
        CURRENT_MAP.write_bytes(r.content)
    m = json.loads(CURRENT_MAP.read_text())
    return {v["ticker"].upper(): int(v["cik_str"]) for v in m.values()}


def _prefix_candidates(ticker: str) -> list:
    t = ticker.lower()
    base = t.split(".")[0]
    cands = [t.replace(".", ""), base]
    return list(dict.fromkeys(cands))


def build(spells: pd.DataFrame, rss: pd.DataFrame, window_start="2009-01-01") -> pd.DataFrame:
    """spells: ticker,start,end (จาก constituents.membership_spells) ; rss: จาก sec_rss.load_all()
    คืน 1 แถวต่อ spell: ticker,start,end,cik,name,sic,method,n_filings,conflict"""
    rss = rss[rss["form"].isin(PERIODIC)].copy()
    cur = load_current_map()
    today = pd.Timestamp.today().normalize()
    sp = spells[(spells["end"].isna()) | (spells["end"] >= pd.Timestamp(window_start))].copy()
    out = []
    for r in sp.itertuples(index=False):
        s = max(r.start, pd.Timestamp(window_start)) - pd.Timedelta(days=365)
        e = (r.end if pd.notna(r.end) else today) + pd.Timedelta(days=180)
        in_win = rss[(rss["filed"] >= s) & (rss["filed"] <= e)]

        # วิธี rss
        hit = in_win[in_win["prefix"].isin(_prefix_candidates(r.ticker))]
        rss_cik = None
        if not hit.empty:
            counts = hit.groupby("cik").size().sort_values(ascending=False)
            rss_cik = int(counts.index[0])

        # วิธี current (+ validate ว่ามี filing ในช่วงนั้นจริง)
        cur_cik = cur.get(r.ticker.upper()) or cur.get(r.ticker.upper().replace(".", "-"))
        cur_valid = cur_cik is not None and (in_win["cik"] == cur_cik).any()

        if rss_cik is not None:
            cik, method = rss_cik, "rss"
        elif cur_valid:
            cik, method = int(cur_cik), "current"
        else:
            cik, method = None, "unmatched"

        conflict = rss_cik is not None and cur_valid and int(cur_cik) != rss_cik
        meta = in_win[in_win["cik"] == cik] if cik is not None else in_win.iloc[0:0]
        out.append({
            "ticker": r.ticker, "start": r.start, "end": r.end, "cik": cik,
            "name": meta["name"].iloc[-1] if len(meta) else None,
            "sic": meta["sic"].dropna().iloc[-1] if meta["sic"].notna().any() else None,
            "method": method, "n_filings": len(meta), "conflict": conflict,
            "alt_cik_current": int(cur_cik) if conflict else None,
        })
    return pd.DataFrame(out)


OVERRIDES = __import__("pathlib").Path(__file__).with_name("cik_overrides.csv")


def spell_candidates(spells: pd.DataFrame, rss: pd.DataFrame, window_start="2009-01-01") -> pd.DataFrame:
    """ผู้สมัคร CIK ต่อ spell: ticker,start,end,cik,n_prefix(จำนวน 10-K ที่ prefix ตรง),is_current"""
    k10 = rss[rss["form"].isin({"10-K", "10-K/A", "10-KT"})]
    per = rss[rss["form"].isin(PERIODIC)]
    cur = load_current_map()
    today = pd.Timestamp.today().normalize()
    rows = []
    for r in spells[(spells["end"].isna()) | (spells["end"] >= pd.Timestamp(window_start))].itertuples(index=False):
        s = max(r.start, pd.Timestamp(window_start)) - pd.Timedelta(days=365)
        e = (r.end if pd.notna(r.end) else today) + pd.Timedelta(days=180)
        hit = k10[k10["prefix"].isin(_prefix_candidates(r.ticker)) & (k10["filed"] >= s) & (k10["filed"] <= e)]
        n = hit.groupby("cik").size().to_dict()
        c = cur.get(r.ticker.upper()) or cur.get(r.ticker.upper().replace(".", "-"))
        if c is not None and ((per["cik"] == c) & (per["filed"] >= s) & (per["filed"] <= e)).any():
            n.setdefault(int(c), 0)
        for cik, cnt in n.items():
            rows.append({"ticker": r.ticker, "start": r.start, "end": r.end, "cik": int(cik),
                         "n_prefix": int(cnt), "is_current": c is not None and int(cik) == int(c)})
    return pd.DataFrame(rows)


def build_segments(cands: pd.DataFrame, tenk: dict, assets: dict, rss: pd.DataFrame,
                   window_start="2009-01-01") -> pd.DataFrame:
    """tenk: cik -> DataFrame[accn, filed] ของ 10-K (จาก companyfacts) ; assets: cik -> median total assets
    คืน segment: ticker,start,end,cik,valid_from,valid_to,method"""
    today = pd.Timestamp.today().normalize()
    k10 = rss[rss["form"].isin({"10-K", "10-K/A", "10-KT"})]
    out = []
    for (t, st, en), g in cands.groupby(["ticker", "start", "end"], dropna=False):
        pre = k10[k10["prefix"].isin(_prefix_candidates(t))]
        eff_s = max(st, pd.Timestamp(window_start))
        eff_e = en if pd.notna(en) else today
        # SEC ticker ปัจจุบันเป็นหลักฐานตัวตนที่แข็งแรง → นับจำนวนปีที่ยื่น 10-K ในช่วง spell เป็นคะแนนแทน prefix
        score = {}
        for x in g.itertuples(index=False):
            sc = x.n_prefix
            if x.is_current:
                d = tenk[x.cik]["filed"] if x.cik in tenk else pd.Series(dtype="datetime64[ns]")
                sc = max(sc, int(((d >= eff_s) & (d <= eff_e + pd.Timedelta(days=180))).sum()))
            score[x.cik] = (sc, assets.get(x.cik, 0) or 0)
        # นับเฉพาะ 10-K ที่ยื่นไม่เกินวันสิ้นสุด spell (กันเลือกบริษัทที่ยื่นงบหลังออกจากดัชนีไปแล้ว)
        fil = {c: (tenk[c][tenk[c]["filed"] <= eff_e] if c in tenk else pd.DataFrame(columns=["accn", "filed"]))
               for c in score}
        dates = {c: pd.to_datetime(f["filed"]) for c, f in fil.items()}
        choice, inc = {}, None
        for y in range(eff_s.year, eff_e.year + 1):
            # หลักฐานรายปี: CIK นี้ยื่น 10-K ที่ prefix ตรงในปี y เอง หรือยื่น 10-K วันเดียวกับ filing ที่ prefix ตรง
            # (combined filing ของบริษัทแม่+บริษัทลูก เช่น utility — RSS แสดงแค่ CIK เดียว)
            py = pre[(pre["filed"].dt.year == y) & (pre["filed"] <= eff_e)]
            # accn ของ filing ที่ prefix ตรง (หาจาก companyfacts ของ CIK ที่ RSS ระบุ, จับด้วยวันที่ยื่น)
            ev_accn, orphan_dates = set(), set()
            for pc, pf in zip(py["cik"], py["filed"]):
                own = fil[pc].loc[fil[pc]["filed"] == pf, "accn"] if pc in fil else pd.Series(dtype=str)
                if len(own):
                    ev_accn |= set(own)
                else:
                    # CIK ใน RSS ไม่มีข้อมูลของตัวเองใน companyfacts (เช่น บริษัทลูกของ utility ที่ยื่นงบรวม)
                    # → ให้เครดิตผู้สมัครที่ยื่น 10-K วันเดียวกัน (บริษัทแม่)
                    orphan_dates.add(pf)
            has_y = {c for c in score if (dates[c].dt.year == y).any()}
            evid = [c for c in has_y if fil[c]["accn"].isin(ev_accn).any() or dates[c].isin(orphan_dates).any()]
            active = evid or [c for c in score if (dates[c].dt.year == y).any()]
            # ปีล่าสุด: ถ้าเจ้าเดิมยื่น 10-K ภายใน 400 วัน ถือว่ายังอยู่ (แค่ยังไม่ถึงรอบยื่นของปีนี้)
            if y == eff_e.year and inc is not None and inc not in active and len(dates[inc]) \
                    and (eff_e - dates[inc].max()).days <= 400:
                active.append(inc)
            if active:
                # คะแนนเท่ากัน → เลือกเจ้าเดิม (continuity) ก่อน แล้วค่อยดู total assets
                choice[y] = inc = max(active, key=lambda c: (score[c][0], c == inc, score[c][1]))
        if not choice:
            out.append({"ticker": t, "start": st, "end": en, "cik": None, "valid_from": st, "valid_to": en, "method": "unmatched"})
            continue
        years = sorted(choice)
        # ปีต้น/ปลายที่ไม่มี 10-K เลย → ใช้ตัวเลือกของปีที่ใกล้ที่สุด
        seq = [(y, choice.get(y)) for y in range(eff_s.year, eff_e.year + 1)]
        last = choice[years[0]]
        filled = []
        for y, c in seq:
            last = c if c is not None else last
            filled.append((y, last))
        segs, cur_c, cur_from = [], filled[0][1], st
        for y, c in filled[1:]:
            if c != cur_c:
                d = dates[c]
                sw = d[d.dt.year == y].min() if (d.dt.year == y).any() else pd.Timestamp(f"{y}-01-01")
                segs.append((cur_c, cur_from, sw - pd.Timedelta(days=1)))
                cur_c, cur_from = c, sw
        segs.append((cur_c, cur_from, en))
        for c, a, b in segs:
            out.append({"ticker": t, "start": st, "end": en, "cik": int(c), "valid_from": a, "valid_to": b,
                        "method": "auto_multi" if len(segs) > 1 else "auto"})
    return pd.DataFrame(out)


def apply_overrides(segs: pd.DataFrame) -> pd.DataFrame:
    """แทนที่ segment อัตโนมัติของ spell ที่มีใน lib/cik_overrides.csv (หลักฐานจาก SEC submissions)"""
    ov = pd.read_csv(OVERRIDES, parse_dates=["spell_start", "valid_from", "valid_to"])
    keys = set(zip(ov["ticker"], ov["spell_start"]))
    keep = segs[[k not in keys for k in zip(segs["ticker"], segs["start"])]].assign(confidence=None, evidence=None)
    spell_end = segs.groupby(["ticker", "start"], dropna=False)["end"].first()
    rows = []
    for x in ov.itertuples(index=False):
        en = spell_end.get((x.ticker, x.spell_start), pd.NaT)
        rows.append({"ticker": x.ticker, "start": x.spell_start, "end": en, "cik": int(x.cik),
                     "valid_from": x.valid_from if pd.notna(x.valid_from) else x.spell_start,
                     "valid_to": x.valid_to if pd.notna(x.valid_to) else en,
                     "method": "override", "confidence": x.confidence, "evidence": x.evidence})
    return pd.concat([keep, pd.DataFrame(rows)], ignore_index=True).sort_values(["ticker", "valid_from"]).reset_index(drop=True)


def cik_changes_within_spell(spells: pd.DataFrame, rss: pd.DataFrame, window_start="2009-01-01") -> pd.DataFrame:
    """diagnostic: spell ที่ CIK (จาก prefix, เฉพาะ 10-K) เปลี่ยนไปตามปี → อาจเป็น reorganization/ticker reuse"""
    k = rss[rss["form"].isin({"10-K", "10-KT"})]
    rows = []
    for r in spells[(spells["end"].isna()) | (spells["end"] >= pd.Timestamp(window_start))].itertuples(index=False):
        e = r.end if pd.notna(r.end) else pd.Timestamp.today()
        h = k[k["prefix"].isin(_prefix_candidates(r.ticker)) & (k["filed"] >= max(r.start, pd.Timestamp(window_start))) & (k["filed"] <= e)]
        if h["cik"].nunique() > 1:
            g = h.groupby("cik").agg(first=("filed", "min"), last=("filed", "max"), n=("filed", "size"), name=("name", "last"))
            for cik, x in g.iterrows():
                rows.append({"ticker": r.ticker, "start": r.start, "end": r.end, "cik": cik, **x.to_dict()})
    return pd.DataFrame(rows)
