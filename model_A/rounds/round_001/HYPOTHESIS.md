# Round 001 — ตระกูล A: สัญญาณเดี่ยว (เขียนก่อนรัน)

## คืออะไร / ทำไม
ทดสอบสัญญาณพื้นฐานทีละตัวภายใต้เกณฑ์ `PREREG_AUTORUN.md` เพื่อดูว่ามีตัวไหน "ชนะขาดรอย" ด้วยตัวเองไหม
และเป็นฐานสำหรับคะแนนรวม (round 002) — ทุกสัญญาณมีที่มาจากงานวิจัย

## สเปก (แน่นอน)
- universe U(d) ตาม PREREG_AUTORUN ข้อ 2; rebalance วันทำการสุดท้ายของ มิ.ย. 2011–2022 (12 รอบ); equal-weight
- เลือก **top 20%** ของหุ้นใน U ที่มีค่าสัญญาณ (ขั้นต่ำ 50 ตัว, เสมอกันเรียงด้วยชื่อ yahoo ticker)
- 2 แบบการจัดอันดับ: overall และ sector-neutral (percentile ภายในกลุ่ม SIC; กลุ่ม < 10 ตัวรวมเป็น "other")
- ต้นทุน 10 และ 25 bps ต่อข้าง; benchmark EW(U) รายปี, SPY

| สัญญาณ | นิยาม (สูง = ดี) | ที่มา | ทิศทางที่คาด | S5 factor |
|---|---|---|---|---|
| Q_GPA | gross profit / TA | Novy-Marx (2013) | + | RMW |
| Q_ROIC | EBIT / (TA − CL − cash) | Greenblatt (2006); ROIC lit. | + | RMW |
| Q_LOWACC | −accruals / avg TA | Sloan (1996) | + | RMW |
| V_BM | equity / mcap | Fama & French (1992) | + | HML |
| V_EP | NI / mcap | Basu (1977) | + | HML |
| V_EBITEV | EBIT / EV | Loughran & Wellman (2011) | + | HML |
| V_FCFP | (CFO − capex) / mcap | Lakonishok et al. (1994) | + | HML |
| I_LOWISS | −ln(หุ้นปีนี้/ปีก่อน, ปรับ split) | Pontiff & Woodgate (2008) | + | CMA |
| I_LOWAG | −การเติบโตของสินทรัพย์ | Cooper, Gulen & Schill (2008) | + | CMA |
| A_FSCORE | Piotroski F (rescale, ≥8/9 ข้อ) เป็นคะแนนจัดอันดับ | Piotroski (2000) | + | RMW |
| A_GSCORE | Mohanram G (8 ข้อ เทียบค่ากลางกลุ่ม SIC, ≥6 ข้อ) | Mohanram (2005) | + | RMW |
| A_ALTMANZ | Altman Z (สูง = ปลอดภัย) | Altman (1968) | + | ไม่มี proxy |
| A_SHY | (ปันผล + ซื้อคืน − ออกหุ้น) / mcap | Boudoukh et al. (2007) | + | HML |
| A_STAB | −std(ROA 3–5 ปี) | earnings stability / QMJ safety | + | RMW |
| A_LOWLEV | −liabilities / TA | QMJ safety (Asness et al. 2019) | + | RMW |

ตัวกรอง (พอร์ต = EW ของ U หลังตัดหุ้นที่ถูก flag; ไม่มีแบบ sector-neutral):
| ตัวกรอง | กฎ | ที่มา | S5 |
|---|---|---|---|
| F_ALTMAN | ตัด Z < 1.81 (distress zone) | Altman (1968) | ไม่มี proxy |
| F_BENEISH | ตัด M > −1.78 (น่าสงสัยว่าแต่งกำไร; คำนวณไม่ได้ = ไม่ตัด) | Beneish (1999) | ไม่มี proxy |
| F_BOTH | ตัดทั้งสองแบบ | — | ไม่มี proxy |

## จำนวน trial
15 สัญญาณ × 2 แบบ + 3 ตัวกรอง = **33 trial** → สะสม 12 + 33 = **45**

## Grid สำหรับ S4 (ประเมินเฉพาะผู้เข้ารอบ; เพื่อนบ้านนับเป็น trial)
- ขนาดพอร์ต q ∈ {10%, **20%**, 30%} (ขั้นต่ำ 50 ตัวคงไว้) → เพื่อนบ้าน = q 10% และ 30% ในแบบการจัดอันดับเดียวกัน
- ตัวกรองไม่มีพารามิเตอร์ต่อเนื่อง → เพื่อนบ้าน = threshold ขั้นถัดไปของงานต้นฉบับ (Altman: 1.23 / 2.99 ของ Z''; ใช้ 1.5 และ 2.99; Beneish: −2.22 และ −1.49)

## ความคาดหมาย (ตรงไปตรงมา)
จากผล v1 (BM ติดลบ, F ใกล้ศูนย์) และงานที่พบว่า anomaly อ่อนลงในหุ้นใหญ่หลังตีพิมพ์ คาดว่า **ไม่น่ามีสัญญาณเดี่ยวผ่าน S1**
(ต้อง Sharpe ≥ SPY + 0.15 ≈ 0.83 และ ≥ EW + 0.15) — ผลลบเป็นผลที่ยอมรับได้
