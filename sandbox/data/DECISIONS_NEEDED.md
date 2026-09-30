# Decisions needed — sector-tagged news collection

Append-only เหมือน `experiments/log.md` — เขียนต่อท้ายเสมอ ไม่ลบของเก่า เปิดไฟล์นี้ก่อน
อย่างอื่นตอนกลับมาเช็คงาน

---

## 2026-09-12 — Group B/C ตัดออกจาก automated collection (ToS + operational blocking)

ตามที่สั่งไว้ ("อย่าอาศัยแค่ robots.txt เป็นเกณฑ์ตัดสิน") เปิดหน้า Terms of Service จริงของ
ทั้ง 5 เว็บใน Group B/C ก่อนเขียน scraper ตัวไหนเลย — ผลคือ **ตัดทั้ง Group B และ Group C
ออกจาก automated collection ทั้งหมด**:

| เว็บ | หลักฐานที่เจอจริง | สรุป |
|---|---|---|
| Seeking Alpha | ToS (`about.seekingalpha.com/terms`) ห้ามชัดเจน: "Use any robot, spider... to download, retrieve, index, 'data mine', 'scrape', 'harvest'..." (Section 6) และห้าม republish/redistribute เนื้อหา (Section 6), อนุญาตแค่ personal non-commercial use (Section 5) | **ตัด** — ToS ห้ามตรงตัว |
| Nasdaq | `robots.txt` และหน้า `agreement-of-use` timeout ทุกครั้งที่ลอง fetch (3 ครั้ง) — เข้าถึงแบบ automated ไม่ได้เลย | **ตัด** — เข้าถึงไม่ได้, ไม่มีทางยืนยัน ToS ได้ |
| ETFDB | `robots.txt` ห้าม `/etfdb/`, `/feeds/insidefutures/`; หน้า `/terms/` และ `/terms-of-use/` คืน 404; **homepage เองคืน 403 Forbidden** ให้ automated fetch | **ตัด** — block ที่ระดับเครือข่ายจริง |
| Schwab | `robots.txt` คืนหน้า authorization error แทนเนื้อหาจริง; หน้า `/terms` fetch ไม่ได้ (error page เดิม) | **ตัด** — block ที่ระดับเครือข่ายจริง |
| Fidelity | `robots.txt` fetch ได้ (มีหลาย path ที่ block แต่ไม่ได้ระบุ `/learn/` ตรงๆ) แต่หน้า terms-of-use 2 URL ที่ลองคืน 400/403 | **ตัด** — เข้าถึงหน้า ToS จริงไม่ได้ (แม้ robots.txt เดี่ยวๆ จะดูผ่าน — ตรงตามที่สั่งว่าอย่าใช้ robots.txt อย่างเดียวตัดสิน)

**สรุป**: ไม่มีเว็บไหนใน Group B/C ผ่านทั้ง 2 เกณฑ์ (ToS อนุญาต + เข้าถึงได้แบบ automated)
เลยสักเว็บเดียว — 1 เว็บห้ามชัดเจนทาง legal (Seeking Alpha), อีก 4 เว็บ block บอทที่ระดับ
เครือข่ายอยู่แล้วไม่ว่า ToS จะว่าไงก็ตาม

**สิ่งที่ต้องการให้ตัดสินใจ**: Group C (Schwab/Fidelity sector commentary) ยังมีทางเลือก
เดิมที่พี่เสนอไว้ — "ปริมาณน้อย ดึงด้วยมือได้" ผมไม่ได้ทำส่วนนี้ต่อ (ไม่ได้ดึงด้วยมือแทน) เพราะ
เป็นงานที่ต้องมีคนนั่งเปิดเว็บ/โหลด PDF เองจริงๆ ไม่ใช่สิ่งที่ script ทำแทนได้ในโหมด
unattended — ถ้าต้องการเนื้อหากลุ่มนี้จริง ต้องเป็นพี่ดึงเองทีละไฟล์ (โครงสร้างไฟล์ปลายทาง
`sector_news_raw/schwab_sector_views/{yyyy-mm}.md` และ
`sector_news_raw/fidelity/{quarter}_{fund_or_report_name}.md` เตรียมไว้ให้แล้วตาม spec เดิม
ยังใช้ได้ถ้าจะ drop ไฟล์เข้าไปเอง แล้วรัน script metadata extraction ทีหลัง — ยังไม่ได้เขียน
script นั้นเพราะรอตัดสินใจว่าจะทำจริงไหมก่อน)

---

## 2026-09-12 — Finnhub `news-sentiment` endpoint ไม่ทำงานบน free tier (403)

Spec เดิมอ้างว่า endpoint `news-sentiment` มี field `sectorAverageBullishPercent`/
`sectorAverageScore` ให้ใช้ตรงๆ — ทดสอบเรียกจริงแล้วได้ `403 Forbidden` (เป็น premium-tier
endpoint ไม่ได้อยู่ใน free tier) **ไม่ใช่การเดา เรียก API จริงแล้วเจอ error นี้**

ใช้ `company-news` endpoint แทน (เรียกได้จริง, ทดสอบแล้ว 200 ตลอด) แต่ endpoint นี้ไม่มี
sentiment score ติดมาด้วย — `sentiment_score` ในไฟล์ `index.csv` สำหรับแถวจาก Finnhub จะเป็น
ค่าว่าง (ไม่ fabricate ตัวเลขขึ้นมาเอง) ต้องมาคิดทีหลังว่าจะรัน FinBERT (เหมือนที่
`src/s4_sentiment.py` ใช้) scoring ข้อความ raw ที่เก็บไว้ยังไงถึงจะได้ sentiment_score
ใส่กลับเข้า index.csv — **ยังไม่ได้ทำส่วนนี้ ต้องการ input ว่าจะให้ทำเลยไหมหรือรอ**

---

## 2026-09-12 — พบว่า `company-news` ของ Finnhub ครอบคลุม sector ETF ticker ได้ตรงๆ เลย
(ไม่ต้อง scrape Group B)

ทดสอบเรียก `company-news?symbol=XLK` (และ XLU, XLRE, XLC, XLB) ตรงๆ ได้ผลจริง (ข่าวที่พูดถึง
sector ETF นั้นชัดเจน เช่น "Sector Update: Tech Stocks Gain Late Afternoon") — แปลว่า
Finnhub เดียวครอบคลุมทั้ง Group A (official API) และเป้าหมายของ Group B (sector ETF news)
ได้พร้อมกันโดยไม่ต้อง scrape เว็บไหนเลย **ตัดสินใจเอง**: ใช้ `company-news` ต่อ ETF ticker
(ทั้ง 11 ตัว) เป็นแหล่งหลักแทน Group B ทั้งหมด — ปรับ scope จาก spec เดิมโดยไม่ต้องถามเพราะ
เป็นการทำได้ดีกว่าด้วยวิธีที่ ToS-compliant กว่า ไม่ใช่การลดขอบเขตงาน

**ข้อมูลสำคัญที่เจอระหว่างทดสอบ**: ถ้า query date range กว้างมาก (เช่น 8.5 เดือนในครั้ง
เดียว) endpoint นี้**ดูเหมือนจะ cap จำนวนผลลัพธ์และ bias ไปทางข่าวล่าสุด** (silently ทิ้งข่าว
เก่ากว่าในช่วงที่ขอไปทั้งที่ query แบบเจาะจงเดือนนั้นตรงๆ กลับได้ผลจริง) — เพื่อไม่ให้ข้อมูล
หาย script นี้เลย query เป็น chunk รายเดือน ไม่ query ช่วงกว้างทีเดียว — เจอด้วยการทดสอบจริง
(ไม่ใช่เดา) ดู `experiments/log.md` สำหรับตัวเลขที่ใช้ยืนยัน

**Free tier rolling window**: ข้อมูลย้อนหลังมีจริงถึงประมาณปลายเดือนกรกฎาคม 2026 เท่านั้น
(เดือนก่อนหน้านั้นทดสอบแล้วว่าง) — ไม่ใช่ archive ยาวเป็นปี เป็น rolling window ล่าสุดเท่านั้น
ตามที่คาดของ free tier ทั่วไป

---

## 2026-09-12 — Benzinga API key ยังไม่มี

`.env` มี `ALPHA_VANTAGE_API_KEY` และ `FINNHUB_API_KEY` พร้อมใช้แล้ว (ทดสอบเรียกจริงสำเร็จ
ทั้งคู่) แต่ **ไม่มี `BENZINGA_API_KEY`** — สมัครเองไม่ได้ (ต้องกรอกอีเมล/ยืนยันตัวตนเอง)
ต้องให้พี่สมัคร Benzinga free tier เอง (benzinga.com/apis) แล้วใส่ `BENZINGA_API_KEY=...`
ใน `.env` ถ้าต้องการให้ทำต่อ — script `collect_benzinga.py` ยังไม่ได้เขียน (จะเขียนพร้อม
ตอนมี key จริงให้ทดสอบ ไม่เขียนแบบเดามาก่อนโดยไม่ได้ลองเรียกจริง)

---

## 2026-09-12 — บั๊กจริงที่เจอ+แก้ระหว่างเขียน `collect_alpha_vantage.py`

1. **cursor ไม่ขยับ (เกือบวนไม่รู้จบ)**: `time_published` จาก API มีวินาที
   (`"20260907T072828"`) แต่ตอนแรก parse ด้วย format ที่ไม่มีวินาที (`%Y%m%dT%H%M`) ทำให้
   `strptime` raise `ValueError` — เดิม `except ValueError: new_cursor = cursor` จับเงียบๆ
   แล้วคง cursor เดิมไว้ ทำให้รันซ้ำ query เดิมได้ผลเดิมตลอด (เจอจากการรันจริง สังเกตว่า
   `new=0` ทุกครั้งทั้งที่ควรมีข่าวใหม่) แก้แล้วโดยแยก format คนละตัวสำหรับ parse
   `time_published` (มีวินาที) กับ format ที่ใช้ส่งใน query (ไม่มีวินาที)
2. **`time_to` เดี่ยวๆ ไม่พอ**: ต้องส่ง `time_from` คู่กันเสมอ ไม่งั้น API ตอบ
   `{"Information": "Invalid inputs..."}` (เจอจากการเรียกจริง) แก้โดย anchor `time_from` ไว้
   ที่ปี 2000 เสมอ (ไม่จำกัดผลจริงเพราะ API เองก็ cap ที่ `limit` ล่าสุดอยู่แล้ว)
3. **สงสัยว่า free tier คืน feed ว่างเฉยๆ ตอนติด rate limit แทนที่จะ error ชัดเจน**: ทดสอบ
   query เดิมเป๊ะ (topic=real_estate, time_to เดิมเป๊ะ) ได้ 1000 บทความตอนแรก แล้วได้ 0
   บทความตอนเรียกซ้ำไม่กี่นาทีถัดมา (ไม่ใช่ error, แค่ `feed: []` เฉยๆ) — **ไม่ยืนยัน 100%
   ว่าเป็น rate limit จริง (อาจเป็นพฤติกรรมปกติของ endpoint ก็ได้) แต่ไม่กล้าเสี่ยง** เลยแก้
   `_exhausted_id`/mark-exhausted-ถาวรออกทั้งหมด เปลี่ยนเป็น "ข้าม topic นั้นแค่รันนี้ ลองใหม่
   ทุกครั้งที่รัน" แทน (ไม่งั้นเสี่ยง mark ผิดแล้วเสียข้อมูลจริงถาวร) เพิ่มการเช็ค key
   `Information`/`Note` ในทุก response ก่อนเชื่อว่า feed ว่างคือ "ไม่มีข้อมูลจริงแล้ว"

## สถานะการเก็บข้อมูล ณ สิ้นวันนี้ (2026-09-12)

- **Finnhub**: เก็บครบ 11 sector ETF ย้อนหลัง ~11-12 เดือน (2025-10-01 ถึง 2026-09-11) —
  **4,512 รายการ**, resumability ทดสอบแล้วว่าทำงานจริง (รันซ้ำ skip ของเดิมหมด ไม่เรียก API
  ซ้ำ) โควต้า Finnhub ไม่ใช่ปัญหา (60/นาที) แทบไม่เหลืออะไรให้ดึงเพิ่มแล้วสำหรับ 11 ตัวนี้
  (อาจมีเพิ่มเรื่อยๆ ตามข่าวใหม่ที่ออกทุกวัน — รัน `collect_finnhub.py` ซ้ำได้เรื่อยๆ)
- **Alpha Vantage**: เก็บได้ **2,664 รายการ** (sector มาจาก ticker mention จริง ไม่ใช่ topic
  label ตรงๆ — แม่นกว่าและครอบคลุมครบทั้ง 11 sector แม้จะ query แค่ 7 topic) ใช้ quota ไปมาก
  วันนี้ (เกือบครบ 25/วัน จากการ debug บั๊กข้างบน) **หยุดไว้ก่อน** cursor ต่อ topic บันทึกไว้
  ใน `collection_log.jsonl` แล้ว พรุ่งนี้รัน `python3 -m sandbox.scripts.collect_alpha_vantage`
  ต่อได้เลย (default `--max-requests 8`) จะเดินต่อจากจุดเดิมอัตโนมัติ
- **รวม**: index.csv มี **7,176 แถว metadata** (ไม่มี raw text หลุดเข้า git — ตรวจแล้วด้วย
  `git status`)
- **Benzinga**: ยังไม่ได้เริ่ม รอ API key
- **Group B (sector ETF ticker news จากเว็บ)**: ไม่ต้องทำแล้ว — Finnhub `company-news` ต่อ
  ETF ticker ครอบคลุมเป้าหมายเดียวกันแล้ว (ดูหัวข้อด้านบน)
- **Group C (Schwab/Fidelity)**: ตัดจาก automated collection แล้ว (ToS + block จริง) รอ
  ตัดสินใจว่าจะดึงด้วยมือไหม
