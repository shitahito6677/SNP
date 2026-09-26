"""
Ken French Data Library — factor รายเดือนรายภูมิภาค ใช้เป็น "ด่านตรวจข้ามตลาด/ข้ามยุค" (S5) เท่านั้น ห้ามใช้จูนพารามิเตอร์
URL ตรวจแล้ว 2026-09-27 (HTTP 200): https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/<name>.zip
ค่าในไฟล์เป็น % ต่อเดือน → แปลงเป็นทศนิยม; ข้อมูลหลัง 2023-06-30 ถูกตัดด้วย lib.guard (held-out lock)
"""

import io
import zipfile

import pandas as pd
import requests

from lib import guard
from lib.paths import RAW

DIR = RAW / "french"
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
REGIONS = {
    "US": ("F-F_Research_Data_5_Factors_2x3_CSV", "F-F_Momentum_Factor_CSV"),
    "Developed_ex_US": ("Developed_ex_US_5_Factors_CSV", "Developed_ex_US_Mom_Factor_CSV"),
    "Europe": ("Europe_5_Factors_CSV", "Europe_Mom_Factor_CSV"),
    "Japan": ("Japan_5_Factors_CSV", "Japan_Mom_Factor_CSV"),
    "Asia_Pacific_ex_Japan": ("Asia_Pacific_ex_Japan_5_Factors_CSV", "Asia_Pacific_ex_Japan_Mom_Factor_CSV"),
    "Emerging": ("Emerging_5_Factors_CSV", "Emerging_MOM_Factor_CSV"),
}


def _read_monthly(name: str) -> pd.DataFrame:
    p = DIR / f"{name}.zip"
    if not p.exists():
        DIR.mkdir(parents=True, exist_ok=True)
        r = requests.get(f"{BASE}/{name}.zip", timeout=60)
        r.raise_for_status()
        p.write_bytes(r.content)
    z = zipfile.ZipFile(p)
    txt = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    rows, header, started = [], None, False
    for line in txt:
        parts = [x.strip() for x in line.split(",")]
        if not started:
            if len(parts) > 1 and parts[0] == "" and any(parts[1:]):
                header, started = parts[1:], True
            continue
        if len(parts[0]) == 6 and parts[0].isdigit():
            rows.append(parts)
        elif rows:  # จบส่วนรายเดือน (ต่อด้วยส่วนรายปี)
            break
    df = pd.DataFrame([r[1:len(header) + 1] for r in rows], columns=header,
                      index=pd.to_datetime([r[0] for r in rows], format="%Y%m") + pd.offsets.MonthEnd(0))
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.mask(df <= -99.99)  # ไฟล์ของ Ken French ใช้ -99.99 / -999 แทน "ไม่มีข้อมูล" (พบใน Emerging)
    df = df / 100
    return guard.clip(df)


def load(region: str) -> pd.DataFrame:
    f5, mom = REGIONS[region]
    a = _read_monthly(f5)
    b = _read_monthly(mom)
    b.columns = ["MOM"]
    return a.join(b, how="left")
