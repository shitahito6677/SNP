"""
ดึง SEC monthly XBRL RSS (https://www.sec.gov/Archives/edgar/monthly/xbrlrss-YYYY-MM.xml)
แล้วย่อเหลือตารางเล็ก ๆ ต่อ filing: cik, ชื่อบริษัท, form, วันที่ยื่น, period, SIC, prefix ของไฟล์ XBRL

ทำไมต้องใช้: SEC `company_tickers.json` มีแต่ ticker ปัจจุบัน หุ้นที่ถูกซื้อกิจการ/ออกจากตลาดไปแล้ว
จะหา CIK ไม่เจอ แต่ไฟล์ schema ของ XBRL (EX-101.SCH) มักตั้งชื่อตาม ticker ณ วันที่ยื่น
เช่น `avb-20121231.xsd` → ใช้ prefix นี้จับคู่ ticker ↔ CIK แบบรู้เวลาได้ (เป็น heuristic ต้องตรวจสอบ)

รัน: python3 -m lib.sec_rss   (จากโฟลเดอร์ model_A) — ไฟล์ดิบ ~23MB/เดือน ลบทิ้งหลัง parse
"""

import re
import sys
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests

from lib.paths import SEC_DIR, SEC_USER_AGENT

RSS_URL = "https://www.sec.gov/Archives/edgar/monthly/xbrlrss-{y}-{m:02d}.xml"
OUT_DIR = SEC_DIR / "xbrlrss_parsed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
KEEP_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "20-F", "40-F"}


def _parse(xml_bytes: bytes) -> pd.DataFrame:
    # SEC เปลี่ยน namespace จาก http:// เป็น https:// ตั้งแต่ปลายปี 2019 → รองรับทั้งสองแบบ
    for ns_uri in ("http://www.sec.gov/Archives/edgar", "https://www.sec.gov/Archives/edgar"):
        df = _parse_ns(xml_bytes, {"edgar": ns_uri})
        if len(df):
            return df
    return df


def _parse_ns(xml_bytes: bytes, NS: dict) -> pd.DataFrame:
    root = ET.fromstring(xml_bytes)
    rows = []
    for item in root.iter("item"):
        f = item.find("edgar:xbrlFiling", NS)
        if f is None:
            continue
        form = (f.findtext("edgar:formType", "", NS) or "").strip()
        if form not in KEEP_FORMS:
            continue
        prefix = None
        for xf in f.iterfind("edgar:xbrlFiles/edgar:xbrlFile", NS):
            if xf.get(f"{{{NS['edgar']}}}type") == "EX-101.SCH":
                name = xf.get(f"{{{NS['edgar']}}}file", "")
                m = re.match(r"([A-Za-z.]+)-", name)
                prefix = m.group(1).lower() if m else None
                break
        rows.append({
            "cik": int(f.findtext("edgar:cikNumber", "0", NS)),
            "name": f.findtext("edgar:companyName", "", NS),
            "form": form,
            "filed": pd.to_datetime(f.findtext("edgar:filingDate", "", NS), format="%m/%d/%Y", errors="coerce"),
            "period": f.findtext("edgar:period", "", NS),
            "sic": pd.to_numeric(f.findtext("edgar:assignedSic", "", NS), errors="coerce"),
            "fye": f.findtext("edgar:fiscalYearEnd", "", NS),
            "prefix": prefix,
        })
    return pd.DataFrame(rows)


def fetch_month(y: int, m: int, session: requests.Session) -> pd.DataFrame:
    out = OUT_DIR / f"{y}-{m:02d}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    for attempt in range(4):
        r = session.get(RSS_URL.format(y=y, m=m), timeout=120)
        if r.status_code == 200:
            break
        time.sleep(2 * (attempt + 1))
    r.raise_for_status()
    df = _parse(r.content)
    if df.empty:
        # ไม่ cache เดือนที่ parse ได้ 0 แถว — เกือบแน่ว่าเป็นปัญหา format ไม่ใช่ไม่มี filing จริง
        raise ValueError(f"{y}-{m:02d}: parse ได้ 0 filing — ตรวจ format ของ RSS")
    df.to_parquet(out, index=False)
    time.sleep(0.2)  # SEC fair-access: ต่ำกว่า 10 req/s มาก
    return df


def fetch_all(start=(2009, 4), end=None) -> pd.DataFrame:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    end = end or (pd.Timestamp.today().year, pd.Timestamp.today().month)
    s = requests.Session()
    s.headers["User-Agent"] = SEC_USER_AGENT
    months = pd.period_range(f"{start[0]}-{start[1]:02d}", f"{end[0]}-{end[1]:02d}", freq="M")
    frames = []
    for p in months:
        try:
            df = fetch_month(p.year, p.month, s)
        except (requests.HTTPError, ValueError) as e:
            print(f"{p}: ERROR {e}", flush=True)
            continue
        frames.append(df)
    print(f"SEC RSS: {len(months)} เดือน, {sum(len(f) for f in frames):,} filings (cache: {OUT_DIR})", flush=True)
    return pd.concat(frames, ignore_index=True)


def load_all() -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p) for p in sorted(OUT_DIR.glob("*.parquet"))], ignore_index=True)


if __name__ == "__main__":
    fetch_all()
    sys.exit(0)
