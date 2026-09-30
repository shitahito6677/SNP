# DATA QUALITY — sandbox v2 prices

สร้างอัตโนมัติ `2026-09-28T05:19:53+00:00` โดย `scripts/data_quality.py` — ห้ามแก้ด้วยมือ

- PRICE_START `2021-02-12` · วันทำการล่าสุด `2026-09-25` · S&P 500 snapshot `2026-09-27`
- สถานะ ticker: **ok** 560, **partial** 15
- data_hash `59dea534989cc08dc0206a8216ffc0794e04b41b0b3c3280d026588fd34fd462`

## สรุปปัญหาที่พบ

| ประเภท | จำนวน ticker | จำนวนครั้ง |
|---|---|---|
| `big_move` | 10 | 11 |
| `unadjusted_split_suspect` | 5 | 8 |

## รายละเอียด

| ticker | ประเภท | n | รายละเอียด |
|---|---|---|---|
| AAP | `big_move` | 1 | 2025-05-22 adj +57.0% close×1.570 |
| APP | `unadjusted_split_suspect` | 1 | 2024-11-07 adj +46.3% close×1.463 |
| BE | `big_move` | 1 | 2024-11-15 adj +59.2% close×1.592 |
| CVNA | `unadjusted_split_suspect` | 1 | 2023-01-12 adj +46.0% close×1.460 |
| CVNA | `big_move` | 1 | 2023-06-08 adj +56.0% close×1.560 |
| ECHO | `unadjusted_split_suspect` | 1 | 2025-06-16 adj +49.1% close×1.491 |
| ECHO | `big_move` | 1 | 2025-08-26 adj +70.2% close×1.702 |
| EPAM | `big_move` | 1 | 2022-02-28 adj -45.7% close×0.543 |
| FMC | `big_move` | 1 | 2025-10-30 adj -46.5% close×0.535 |
| GL | `big_move` | 1 | 2024-04-11 adj -53.1% close×0.469 |
| HOOD | `unadjusted_split_suspect` | 1 | 2021-08-04 adj +50.4% close×1.504 |
| LUMN | `big_move` | 1 | 2024-08-06 adj +93.1% close×1.931 |
| MRNA | `big_move` | 1 | 2026-08-19 adj +177.0% close×2.770 |
| PARA | `big_move` | 1 | 2024-01-05 adj +54.8% close×1.548 |
| PARA | `unadjusted_split_suspect` | 1 | 2024-09-20 adj +97.6% close×1.976 |
| PARA | `unadjusted_split_suspect` | 1 | 2024-09-24 adj +96.2% close×1.962 |
| PARA | `big_move` | 1 | 2024-10-09 adj +81.9% close×1.819 |
| PARA | `unadjusted_split_suspect` | 1 | 2024-12-10 adj +47.5% close×1.475 |
| PARA | `unadjusted_split_suspect` | 1 | 2025-01-29 adj +54.4% close×1.544 |

## missing (0) — ตัดทิ้ง (ผู้ใช้อนุญาต)

—

## partial (15)

| ticker | ช่วง | เหตุผล |
|---|---|---|
| APP | 2021-04-15 → 2026-09-25 | เริ่ม 2021-04-15 (เข้า index/IPO หลัง PRICE_START) |
| CEG | 2022-01-19 → 2026-09-25 | เริ่ม 2022-01-19 (เข้า index/IPO หลัง PRICE_START) |
| COIN | 2021-04-14 → 2026-09-25 | เริ่ม 2021-04-14 (เข้า index/IPO หลัง PRICE_START) |
| FDXF | 2026-05-27 → 2026-09-25 | เริ่ม 2026-05-27 (เข้า index/IPO หลัง PRICE_START) |
| GEHC | 2022-12-15 → 2026-09-25 | เริ่ม 2022-12-15 (เข้า index/IPO หลัง PRICE_START) |
| GEV | 2024-03-27 → 2026-09-25 | เริ่ม 2024-03-27 (เข้า index/IPO หลัง PRICE_START) |
| HONA | 2026-06-15 → 2026-09-25 | เริ่ม 2026-06-15 (เข้า index/IPO หลัง PRICE_START) |
| HOOD | 2021-07-29 → 2026-09-25 | เริ่ม 2021-07-29 (เข้า index/IPO หลัง PRICE_START) |
| KVUE | 2023-05-04 → 2026-09-25 | เริ่ม 2023-05-04 (เข้า index/IPO หลัง PRICE_START) |
| OGN | 2021-05-14 → 2026-09-25 | เริ่ม 2021-05-14 (เข้า index/IPO หลัง PRICE_START) |
| Q | 2025-10-27 → 2026-09-25 | เริ่ม 2025-10-27 (เข้า index/IPO หลัง PRICE_START) |
| RDDT | 2024-03-21 → 2026-09-25 | เริ่ม 2024-03-21 (เข้า index/IPO หลัง PRICE_START) |
| SNDK | 2025-02-13 → 2026-09-25 | เริ่ม 2025-02-13 (เข้า index/IPO หลัง PRICE_START) |
| SOLV | 2024-03-26 → 2026-09-25 | เริ่ม 2024-03-26 (เข้า index/IPO หลัง PRICE_START) |
| VLTO | 2023-10-04 → 2026-09-25 | เริ่ม 2023-10-04 (เข้า index/IPO หลัง PRICE_START) |

หมายเหตุ: `big_move` = ผลตอบแทนรายวัน > 45% ที่ไม่ตรงอัตราส่วน split — ส่วนใหญ่เป็นเหตุการณ์จริง (ควบรวม/ข่าวแรง) แต่ควรตรวจด้วยตาก่อนเชื่อผล; `unadjusted_split_suspect` = Close กระโดดตรงอัตราส่วน split และ Adj Close กระโดดตาม → Yahoo อาจไม่ได้ปรับ split
