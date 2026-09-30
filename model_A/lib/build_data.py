"""
Pipeline เตรียมข้อมูลของ Model A (idempotent — มี cache ทุกขั้น รันซ้ำได้ไม่ดาวน์โหลดซ้ำ)

  1. constituents  → data/interim/spells.parquet          (ช่วงที่แต่ละ ticker อยู่ใน S&P 500)
  2. SEC RSS       → data/raw/sec/xbrlrss_parsed/*.parquet (lib.sec_rss)
  3. CIK map       → data/interim/cik_map.parquet (diagnostic ต่อ spell), cik_candidates.parquet,
                     cik_segments.parquet (ตัวที่ใช้จริง: CIK ต่อช่วงเวลา หลัง override)
  4. companyfacts  → data/raw/sec/companyfacts/*.json.gz (ของผู้สมัครทุกตัว)
  5. annual facts  → data/interim/annual_long.parquet, annual_wide.parquet
  6. prices        → data/raw/prices/*.parquet             (lib.prices)

รัน: python3 -m lib.build_data   (จากโฟลเดอร์ model_A)
"""

import pandas as pd
import requests

from lib import checks, cik_map, constituents, prices, sec_facts, sec_rss
from lib.paths import INTERIM, SEC_USER_AGENT

WINDOW_START = "2009-01-01"  # XBRL เริ่มบังคับใช้กลางปี 2009 → ก่อนหน้านี้ไม่มีงบให้ใช้
BENCHMARKS = ["SPY", "RSP", "^GSPC", "^DJI", "^SET.BK", "TDEX.BK", "THD", "THB=X"]


def build_spells() -> pd.DataFrame:
    p = INTERIM / "spells.parquet"
    if not p.exists():
        constituents.membership_spells(constituents.load_history()).to_parquet(p, index=False)
    return pd.read_parquet(p)


def build_cik_map(spells: pd.DataFrame) -> pd.DataFrame:
    p = INTERIM / "cik_map.parquet"
    if not p.exists():
        cik_map.build(spells, sec_rss.load_all(), window_start=WINDOW_START).to_parquet(p, index=False)
    return pd.read_parquet(p)


def fetch_companyfacts(ciks) -> list:
    """ดาวน์โหลด companyfacts (cache) คืนรายการ cik ที่ SEC ไม่มีข้อมูล (404)"""
    s = requests.Session()
    s.headers["User-Agent"] = SEC_USER_AGENT
    missing = []
    for i, cik in enumerate(sorted(set(int(c) for c in ciks))):
        if not sec_facts.fetch(cik, s):
            missing.append(cik)
        if (i + 1) % 100 == 0:
            print(f"companyfacts {i + 1}/{len(set(ciks))}", flush=True)
    return missing


def build_segments(spells: pd.DataFrame) -> pd.DataFrame:
    p = INTERIM / "cik_segments.parquet"
    if p.exists():
        return pd.read_parquet(p)
    rss = sec_rss.load_all()
    cands = cik_map.spell_candidates(spells, rss, window_start=WINDOW_START)
    cands.to_parquet(INTERIM / "cik_candidates.parquet", index=False)
    ov = pd.read_csv(cik_map.OVERRIDES)
    missing = fetch_companyfacts(list(cands["cik"]) + list(ov["cik"]))
    pd.Series(missing, name="cik").to_csv(INTERIM / "companyfacts_404.csv", index=False)
    prof = {c: sec_facts.tenk_profile(c) for c in cands["cik"].unique()}
    segs = cik_map.build_segments(cands, {c: v[0] for c, v in prof.items()}, {c: v[1] for c, v in prof.items()},
                                  rss, window_start=WINDOW_START)
    # spell ที่ไม่มีผู้สมัครเลย → unmatched
    sp = spells[(spells["end"].isna()) | (spells["end"] >= pd.Timestamp(WINDOW_START))]
    have = set(zip(segs["ticker"], segs["start"]))
    none = sp[[k not in have for k in zip(sp["ticker"], sp["start"])]]
    segs = pd.concat([segs, none.assign(cik=None, valid_from=none["start"], valid_to=none["end"], method="unmatched")],
                     ignore_index=True)
    segs = cik_map.apply_overrides(segs)
    segs.to_parquet(p, index=False)
    return segs


def build_facts(segs: pd.DataFrame) -> tuple:
    pl, pw = INTERIM / "annual_long.parquet", INTERIM / "annual_wide.parquet"
    if pl.exists() and pw.exists():
        return pd.read_parquet(pl), pd.read_parquet(pw)
    ciks = sorted(segs["cik"].dropna().astype(int).unique())
    missing = fetch_companyfacts(ciks)
    long = pd.concat([sec_facts.first_filed_annual(c) for c in ciks if c not in missing], ignore_index=True)
    wide = sec_facts.annual_wide(long)
    long.to_parquet(pl, index=False)
    wide.to_parquet(pw, index=False)
    return long, wide


def build_prices(spells: pd.DataFrame) -> None:
    tick = spells[(spells["end"].isna()) | (spells["end"] >= pd.Timestamp(WINDOW_START))]["ticker"]
    prices.download([constituents.to_yahoo(t) for t in tick] + BENCHMARKS, start="2008-01-01")


def run():
    spells = build_spells()
    checks.nonempty(spells, "spells", 1000)
    checks.nonempty(sec_rss.fetch_all(), "SEC RSS filings", 100_000)
    build_cik_map(spells)
    segs = build_segments(spells)
    checks.nonempty(segs, "cik_segments", 800)
    checks.segments_valid(segs)
    long, wide = build_facts(segs)
    checks.nonempty(long, "annual_long", 100_000)
    checks.unique_keys(wide, ["cik", "period_end"], "annual_wide")
    build_prices(spells)
    checks.nonempty(prices.load_adj_close(), "prices", 4000)


if __name__ == "__main__":
    run()
