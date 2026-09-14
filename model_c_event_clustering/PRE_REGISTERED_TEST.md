# exp_04 — Pre-registered validation test (เขียนก่อนรัน Phase E5)

**สถานะตอนเขียนไฟล์นี้:** Phase E1-E3 เสร็จแล้ว (price paths, features, cluster assignments)
**ยังไม่ได้ join กับ `sector_impact_score`/channel score จาก `exp_03` เลยแม้แต่ครั้งเดียว** —
ไฟล์นี้เขียนและ commit ก่อนเห็นตัวเลขผลทดสอบใดๆ ทั้งสิ้น ตามกฎ "ห้าม fishing" ที่กำหนดไว้ ตรวจสอบ
ย้อนหลังได้จาก git log ว่า commit ของไฟล์นี้มี timestamp ก่อน commit ของ Phase E5 เสมอ

## 1. คำถามวิจัย

`sector_impact_score` (คะแนนรวม) และ/หรือ channel score รายช่อง (C1-C7) จาก `exp_03` Phase R4
แยกความแตกต่างระหว่าง cluster ของรูปแบบราคา (price-path shape) ที่เจอใน `exp_04` Phase E3 ได้
อย่างมีนัยสำคัญทางสถิติหรือไม่ — กล่าวคือ ข่าวที่ rule engine ให้คะแนนต่างกัน มีแนวโน้มตกอยู่ใน
cluster รูปแบบราคาที่ต่างกันจริงหรือไม่

**เป้าหมายของ exp_04 คือ triangulate ผลลบของ exp_03/R5 ด้วยวิธีที่ต่างไป ไม่ใช่พยายามหาผลบวก** —
ถ้าไม่พบความแตกต่างที่มีนัยสำคัญ (เหมือน R5) นั่นคือหลักฐานยืนยันผลลบเดิมที่แข็งแรงขึ้น ไม่ใช่
ความล้มเหลวของ exp_04

## 2. ขอบเขตการทดสอบ

ทดสอบเฉพาะ **sector ที่ Phase E3 พบว่ามี cluster เสถียร** (bootstrap ARI >= 0.5 ที่ k ที่เลือก)
เท่านั้น — sector ที่ E3 สรุปว่าไม่มี cluster เสถียรจะไม่ถูกนำมาทดสอบใน E5 (ไม่มีอะไรให้เทียบ
ระหว่างกลุ่ม)

ตัวแปรที่ทดสอบต่อ sector: `sector_impact_score` (คะแนนรวมจาก R4) เป็นหลัก และ 7 channel score
(`C1`-`C7`) เป็นการทดสอบเสริม (exploratory รอง — ผลหลักที่ใช้ตัดสิน pass/fail คือ
`sector_impact_score` เท่านั้น เพื่อกัน multiple-comparison inflation จากการทดสอบ 8 ตัวแปรแล้ว
เลือกเอาตัวที่ดูดีที่สุดมารายงาน)

## 3. Metric

**Kruskal-Wallis H-test** (ไม่ใช้ one-way ANOVA เพราะ abnormal return ไม่ normal distribution
ตามที่ทราบจากงานก่อนหน้า) เทียบการกระจายของ `sector_impact_score` ระหว่างกลุ่ม cluster (k กลุ่ม
ตามที่ E3 เลือกไว้แต่ละ sector)

**Effect size:** eta-squared แบบ non-parametric ประมาณจากสถิติ Kruskal-Wallis:
```
eta_squared = (H - k + 1) / (n - k)
```
โดย H = Kruskal-Wallis H statistic, k = จำนวน cluster, n = จำนวนข่าวทั้งหมดใน sector นั้น
(สูตรมาตรฐานสำหรับประมาณ eta-squared จากผล Kruskal-Wallis — ดู Tomczak & Tomczak, 2014)

## 4. เกณฑ์ผ่าน/ไม่ผ่าน (fix ไว้ตรงนี้ ห้ามเปลี่ยนหลังเห็นผล E5)

Sector หนึ่งจะถือว่า **"ผ่าน" (มีสัญญาณ)** ก็ต่อเมื่อพร้อมกันทั้ง 2 ข้อ:
1. `p < 0.05` (Kruskal-Wallis)
2. `eta_squared > 0.06` (medium effect ตามเกณฑ์ของ Cohen — กัน sample size ใหญ่ (n=424 บาง
   sector) ทำให้ p ต่ำได้ง่ายโดยไม่มี effect ขนาดที่มีความหมายจริง)

**ไม่มีการปรับ threshold (Bonferroni ฯลฯ) สำหรับการทดสอบหลายๆ sector พร้อมกัน** — รายงานผลดิบ
ทุก sector ตรงไปตรงมา ถ้ามี sector ไหนผ่านเกณฑ์ท่ามกลาง sector อื่นที่ไม่ผ่าน ต้องระบุไว้ชัดว่า
เป็นไปได้ว่าเป็น false positive จาก multiple testing (11 sector ทดสอบพร้อมกัน) ไม่ใช่รีบสรุปว่า
sector นั้นมีสัญญาณจริง

## 5. Triangulation check (บังคับรายงานคู่กับผลทุกครั้ง)

สำหรับทุก sector ที่ทดสอบ ต้องเทียบผลกับ `exp_03`/R5 (Spearman rho ระหว่าง sector_impact_score
กับ CAR จริง, `model_c_rulebase/data/r5_rho_table.csv`, level=`by_sector`):
- **สอดคล้องกัน (ทั้งคู่ negative):** ยืนยันผลลบเดิมด้วยวิธีที่ต่างไป — หลักฐานแข็งแรงขึ้น
- **ขัดแย้งกัน** (เช่น sector ผ่านเกณฑ์ exp_04 แต่ R5 ก็ยังบอกว่าไม่มีสัญญาณ, หรือกลับกัน): **ตั้ง
  เป็นคำถามเปิดไว้ ไม่รีบสรุปว่าใครถูกใครผิด** — วิธีวัดต่างกัน (correlation กับ CAR endpoint เดียว
  vs. การแยก cluster รูปแบบราคาทั้งเส้น) อาจจับสัญญาณคนละมุมกันได้จริงโดยไม่ขัดแย้งกันเชิงตรรกะ

## 6. ขั้นตอนถัดไปตามผล

- **ถ้าไม่มี sector ไหนผ่านเกณฑ์เลย:** negative result ที่ยืนยัน exp_03 — บันทึกและปิด exp_04
  โดยไม่ทำอะไรเพิ่ม (ไม่มี "Phase E6 calibration" ใน exp_04 นี้ เพราะเป้าหมายคือ triangulate ไม่ใช่
  สร้างโมเดลใหม่)
- **ถ้ามี sector ผ่านเกณฑ์บางส่วน:** รายงานตรงไปตรงมาว่า sector ไหน, ตัวเลขเท่าไหร่, ตั้งคำถาม
  เปิดตามข้อ 5 ไม่ฟันธงว่าเป็นสัญญาณจริงจนกว่าจะมีการทดสอบยืนยันเพิ่มเติมในอนาคต (นอกขอบเขต
  exp_04 นี้)

---
*ไฟล์นี้ต้อง commit ก่อน Phase E5 เสมอ — ห้ามแก้ไขเนื้อหาข้อ 1-4 หลัง commit ของ Phase E5 เกิดขึ้น
แล้ว (ตรวจสอบด้วย git log ได้ทุกเมื่อ)*
