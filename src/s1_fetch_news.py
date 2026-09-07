"""
s1_fetch_news.py — ขั้นที่ 1: ดึงข่าวเศรษฐกิจมหภาคสหรัฐฯ ย้อนหลังให้มากที่สุด

แหล่งข้อมูลที่พยายามดึง:
    1. FOMC statements       — federalreserve.gov              (1996 - ปัจจุบัน)
    2. Beige Book (แหล่งเสริม) — federalreserve.gov              (1996 - ปัจจุบัน)
    3. CPI news release      — bls.gov                          (ดัชนีเงินเฟ้อ)
    4. Employment Situation  — bls.gov                          (ตัวเลขจ้างงาน/NFP)

กติกาสำคัญ: ห้ามสร้าง/แต่งข้อมูลข่าวปลอมเด็ดขาด
    ถ้าแหล่งไหนดึงไม่ได้ (network error / HTTP error / ถูกบล็อก) จะ "ข้าม" แหล่งนั้น
    และบันทึกเหตุผลไว้ใน SKIPPED_SOURCES เพื่อรายงานให้ผู้ใช้ทราบ — ไม่มีการเดาหรือ
    generate ข้อความมาแทนของจริง

ผลลัพธ์: data/raw/macro_news_raw.parquet  (คอลัมน์: date, text, source, url)

หมายเหตุเรื่อง CPI / Employment Situation (bls.gov):
    ตอนพัฒนาสคริปต์นี้ เครือข่ายที่ใช้รันถูก bls.gov บล็อกทั้งโดเมน (403 Access Denied,
    WAF-level block ไม่เกี่ยวกับ User-Agent) โค้ดส่วนนี้เขียนตามโครงสร้างหน้าเว็บ
    bls.gov ที่ทราบ (หน้ารายการข่าวเก่า /bls/news-release/cpi.htm และ
    /bls/news-release/empsit.htm ซึ่งลิงก์ไปที่ /news.release/archives/<name>_MMDDYYYY.htm)
    แต่ "ยังไม่ได้ยืนยันด้วยการรันจริงให้สำเร็จ" เนื่องจากถูกบล็อก — ถ้ารันจากเครือข่ายอื่น
    ที่เข้าถึง bls.gov ได้ ควรตรวจสอบ selector ของเนื้อหาอีกครั้ง
"""

import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

BASE_FED = "https://www.federalreserve.gov"
BASE_BLS = "https://www.bls.gov"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = PROJECT_ROOT / "data" / "raw" / "macro_news_raw.parquet"

REQUEST_DELAY = 0.3   # วินาที หน่วงระหว่าง request แต่ละครั้ง (มารยาทต่อ server)
TIMEOUT = 20
RETRIES = 2
START_YEAR = 1996      # ปีเริ่มต้นที่ federalreserve.gov มี archive ให้ดึง

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("s1_fetch_news")

session = requests.Session()
session.headers.update(HEADERS)

# แหล่งที่ข้ามไป พร้อมเหตุผล (ห้ามเดาแทนที่)
SKIPPED_SOURCES = []


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def fetch(url, retries=RETRIES, timeout=TIMEOUT):
    """GET url, คืน requests.Response ถ้าสำเร็จ (HTTP 200), คืน None ถ้าไม่สำเร็จ"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=timeout)
            time.sleep(REQUEST_DELAY)
            if r.status_code == 200:
                return r, None
            last_err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(1.0 * (attempt + 1))
    log.warning(f"fetch failed: {url} ({last_err})")
    return None, last_err


def fetch_ok(url, **kw):
    """เหมือน fetch() แต่คืนแค่ Response หรือ None (สำหรับที่ไม่ต้องใช้เหตุผล error)"""
    r, _err = fetch(url, **kw)
    return r


def extract_main_text(html):
    """ดึงเนื้อหาหลักจาก HTML โดยลองหลาย selector (เว็บ federalreserve.gov
    เปลี่ยน CMS หลายครั้งในรอบ 30 ปี โครงสร้างหน้าเลยไม่เหมือนกันทุกยุค)"""
    soup = BeautifulSoup(html, "lxml")
    for sel in ["div#article", "div.col-xs-12.col-sm-8.col-md-8", "main", "body"]:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text("\n", strip=True)
            if len(txt) > 100:
                return txt
    return None


def parse_date_from_url(url):
    """พยายามดึงวันที่จาก pattern YYYYMMDD ที่ฝังอยู่ใน URL"""
    m = re.search(r"(\d{8})", url)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date().isoformat()
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# Source 1: FOMC statements (federalreserve.gov)
# --------------------------------------------------------------------------

def fomc_index_url(year):
    if year <= 2005:
        return f"{BASE_FED}/newsevents/press/all/{year}all.htm"
    elif year <= 2015:
        return f"{BASE_FED}/newsevents/pressreleases/{year}all.htm"
    elif year <= 2019:
        # 2016-2019 ไม่มีหน้า "{year}-press-fomc.htm" (404) ใช้หน้ารวมข่าวทั้งหมดของปีแทน
        return f"{BASE_FED}/newsevents/pressreleases/{year}-press.htm"
    else:
        return f"{BASE_FED}/newsevents/pressreleases/{year}-press-fomc.htm"


def fetch_fomc_statements(start_year=START_YEAR, end_year=None):
    end_year = end_year or datetime.now().year
    log.info(f"[FOMC] collecting statement links, years {start_year}-{end_year}")

    stmt_urls = []
    seen = set()
    unreachable_years = []

    for year in range(start_year, end_year + 1):
        idx_url = fomc_index_url(year)
        r = fetch_ok(idx_url)
        if r is None:
            unreachable_years.append(year)
            continue
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            low = text.lower()
            if "fomc statement" not in low:
                continue
            if "longer-run goals" in low:  # ไม่ใช่แถลงการณ์หลังประชุม ข้าม
                continue
            href = urljoin(BASE_FED, a["href"])
            if href not in seen:
                seen.add(href)
                stmt_urls.append(href)

    if unreachable_years:
        log.warning(f"[FOMC] index pages unreachable for years: {unreachable_years}")

    log.info(f"[FOMC] found {len(stmt_urls)} statement URLs, fetching content...")

    records = []
    failed = []
    for i, url in enumerate(stmt_urls, 1):
        r = fetch_ok(url)
        if r is None:
            failed.append(url)
            continue
        text = extract_main_text(r.text)
        if not text:
            failed.append(url)
            continue
        date = parse_date_from_url(url)
        records.append({"date": date, "text": text, "source": "FOMC_statement", "url": url})
        if i % 50 == 0:
            log.info(f"[FOMC] fetched {i}/{len(stmt_urls)}")

    if failed:
        log.warning(f"[FOMC] {len(failed)} statement pages failed to fetch/parse (skipped)")

    if not records:
        SKIPPED_SOURCES.append({
            "source": "FOMC_statement",
            "reason": "ไม่สามารถดึงข้อมูลได้เลยแม้แต่รายการเดียว (index pages หรือ statement pages ล้มเหลวทั้งหมด)",
        })

    log.info(f"[FOMC] done: {len(records)} statements collected")
    return records


# --------------------------------------------------------------------------
# Source 2: Beige Book (federalreserve.gov) — แหล่งเสริม
# --------------------------------------------------------------------------

MONTH_DAY_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})"
)


def fetch_beige_book(start_year=START_YEAR, end_year=None):
    end_year = end_year or datetime.now().year
    log.info(f"[BeigeBook] collecting report links, years {start_year}-{end_year}")

    # (index_url, year_hint) — year_hint ใช้ประกอบวันที่ตอนหน้า index ไม่มีวันที่แบบ
    # 8 หลักฝังใน URL (CMS รุ่นหลังของ federalreserve.gov ใช้ URL แค่ YYYYMM ไม่มีวันที่)
    index_urls = [(f"{BASE_FED}/monetarypolicy/beigebook{y}.htm", y) for y in range(start_year, end_year)]
    index_urls.append((f"{BASE_FED}/monetarypolicy/beige-book-default.htm", datetime.now().year))  # ปีปัจจุบัน

    report_urls = []
    date_hints = {}  # href -> ISO date string ที่ parse ได้จากข้อความข้าง link บน index page
    seen = set()
    unreachable = []

    for idx_url, year_hint in index_urls:
        r = fetch_ok(idx_url)
        if r is None:
            unreachable.append(idx_url)
            continue
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True).upper() != "HTML":
                continue
            href = a["href"]
            if "beigebook" not in href.lower():
                continue
            href = urljoin(BASE_FED, href)

            # หาวันที่จากข้อความรอบๆ link บน index page เช่น "January 15 | HTML | PDF"
            parent = a.find_parent(["tr", "li", "div", "p"])
            if parent is not None:
                m = MONTH_DAY_RE.search(parent.get_text(" ", strip=True))
                if m:
                    year_for_date = year_hint
                    # ถ้าเป็นหน้า current-year แต่เดือนที่เจอคือธันวาคม ทั้งที่ตอนนี้เป็นต้นปี
                    # (เช่น ม.ค./ก.พ.) แสดงว่าเป็นรายงานของปีก่อนหน้าที่ค้างอยู่บนหน้า default
                    if year_hint == datetime.now().year and m.group(1) == "December" and datetime.now().month <= 2:
                        year_for_date = year_hint - 1
                    try:
                        dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {year_for_date}", "%B %d %Y")
                        date_hints[href] = dt.date().isoformat()
                    except ValueError:
                        pass

            if href not in seen:
                seen.add(href)
                report_urls.append(href)

    if unreachable:
        log.warning(f"[BeigeBook] {len(unreachable)} index pages unreachable")

    log.info(f"[BeigeBook] found {len(report_urls)} report URLs, fetching content...")

    records = []
    failed = []
    no_date = []
    for i, url in enumerate(report_urls, 1):
        r = fetch_ok(url)
        if r is None:
            failed.append(url)
            continue
        text = extract_main_text(r.text)
        if not text:
            failed.append(url)
            continue
        # ลำดับความสำคัญ: 8 หลักใน URL (แม่นยำสุด) -> วันที่ parse จาก index page
        date = parse_date_from_url(url) or date_hints.get(url)
        if not date:
            no_date.append(url)
            continue
        records.append({"date": date, "text": text, "source": "Beige_Book", "url": url})
        if i % 50 == 0:
            log.info(f"[BeigeBook] fetched {i}/{len(report_urls)}")

    if failed:
        log.warning(f"[BeigeBook] {len(failed)} report pages failed to fetch/parse (skipped)")
    if no_date:
        log.warning(f"[BeigeBook] {len(no_date)} report pages fetched but no date could be determined (skipped, not guessed)")

    if not records:
        SKIPPED_SOURCES.append({
            "source": "Beige_Book",
            "reason": "ไม่สามารถดึงข้อมูลได้เลยแม้แต่รายการเดียว",
        })

    log.info(f"[BeigeBook] done: {len(records)} reports collected")
    return records


# --------------------------------------------------------------------------
# Source 3: CPI news release (bls.gov)
# --------------------------------------------------------------------------

def fetch_bls_series(index_url, archive_prefix, source_name):
    """โครงสร้างทั่วไปของหน้า archive ข่าว bls.gov: หน้า index มีลิงก์ไปยัง
    /news.release/archives/<prefix>_MMDDYYYY.htm ของแต่ละรอบประกาศ
    หมายเหตุ: ยังไม่ได้ยืนยันด้วยการรันจริงสำเร็จ (bls.gov บล็อกเครือข่ายนี้ทั้งโดเมน)"""
    r = fetch_ok(index_url)
    if r is None:
        SKIPPED_SOURCES.append({
            "source": source_name,
            "reason": f"เข้าถึง {index_url} ไม่ได้ (bls.gov บล็อก request จากเครือข่ายนี้ทั้งโดเมน — "
                      f"ทดสอบแล้วได้ HTTP 403 Access Denied จาก WAF ไม่ว่าจะเปลี่ยน User-Agent "
                      f"หรือ path ใดก็ตาม)",
        })
        return []

    soup = BeautifulSoup(r.text, "lxml")
    release_urls = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if f"archives/{archive_prefix}" not in href.lower():
            continue
        href = urljoin(BASE_BLS, href)
        if href not in seen:
            seen.add(href)
            release_urls.append(href)

    if not release_urls:
        SKIPPED_SOURCES.append({
            "source": source_name,
            "reason": f"เข้าถึง index page ({index_url}) ได้ แต่ไม่พบลิงก์ archive ตาม pattern ที่คาดไว้",
        })
        return []

    log.info(f"[{source_name}] found {len(release_urls)} release URLs, fetching content...")
    records = []
    failed = []
    for i, url in enumerate(release_urls, 1):
        r = fetch_ok(url)
        if r is None:
            failed.append(url)
            continue
        text = extract_main_text(r.text)
        if not text:
            failed.append(url)
            continue
        date = parse_date_from_url(url)
        records.append({"date": date, "text": text, "source": source_name, "url": url})

    if failed:
        log.warning(f"[{source_name}] {len(failed)} release pages failed to fetch/parse (skipped)")

    log.info(f"[{source_name}] done: {len(records)} releases collected")
    return records


def fetch_cpi_releases():
    return fetch_bls_series(f"{BASE_BLS}/bls/news-release/cpi.htm", "cpi_", "CPI_release")


def fetch_nfp_releases():
    return fetch_bls_series(f"{BASE_BLS}/bls/news-release/empsit.htm", "empsit_", "NFP_release")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    all_records = []

    all_records += fetch_fomc_statements()
    all_records += fetch_cpi_releases()
    all_records += fetch_nfp_releases()
    all_records += fetch_beige_book()

    if not all_records:
        log.error("ไม่มีข้อมูลใดถูกดึงมาได้เลย — หยุดโดยไม่สร้างไฟล์ผลลัพธ์")
        sys.exit(1)

    df = pd.DataFrame(all_records)
    df = df.dropna(subset=["date", "text"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["source", "url"])
    df = df.sort_values(["date", "source"]).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)

    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"Total rows saved: {len(df)}")
    log.info("By source:\n" + df["source"].value_counts().to_string())
    log.info(f"Date range: {df['date'].min().date()} -> {df['date'].max().date()}")
    log.info(f"Saved to: {OUT_PATH}")

    if SKIPPED_SOURCES:
        log.warning("=" * 60)
        log.warning("SKIPPED SOURCES (ห้ามเดาแทน — ต้องรายงานให้ผู้ใช้ทราบ)")
        log.warning("=" * 60)
        for s in SKIPPED_SOURCES:
            log.warning(f"- {s['source']}: {s['reason']}")

    return df


if __name__ == "__main__":
    main()
