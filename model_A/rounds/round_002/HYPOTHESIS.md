# Round 002 — ตระกูล B: คะแนนรวม (เขียนก่อนรัน)

## คืออะไร / ทำไม
งานวิจัยพบว่าการรวม "คุณภาพ" กับ "ความถูก" ให้ผลดีกว่าใช้มุมเดียว (Novy-Marx 2013; Asness, Frazzini & Pedersen 2019 "QMJ";
Li & Mohanram 2019) — round 001 พบว่าสัญญาณเดี่ยวไม่เสถียร คะแนนรวมอาจลดความผันผวนของสัญญาณ

## สเปก (แน่นอน) — ส่วนที่ไม่ได้ระบุใช้เหมือน round 001
- องค์ประกอบ: percentile rank ของแต่ละสัญญาณภายใน U ณ วัน R (เฉพาะหุ้นที่มีค่า); แบบ sector-neutral ใช้ percentile ภายในกลุ่ม SIC
- เสา (pillar) = ค่าเฉลี่ยของ rank ขององค์ประกอบที่มีค่า (ต้องมี ≥ 1); คะแนนรวม = ค่าเฉลี่ยเท่ากันของเสา (ต้องมีครบทุกเสา)
- เลือก top 20% ของหุ้นที่มีคะแนนรวม (ขั้นต่ำ 50 ตัว), EW, rebalance มิ.ย. 2011–2022, ต้นทุน 10/25 bps

| รหัส | เสา (น้ำหนักเท่ากัน) | ที่มา | S5 factor |
|---|---|---|---|
| B_QV | Quality {Q_GPA, Q_ROIC, Q_LOWACC} + Value {V_BM, V_EP, V_EBITEV, V_FCFP} | Novy-Marx (2013) | (RMW+HML)/2 |
| B_QUAL | Profitability {Q_GPA, Q_ROIC, Q_LOWACC} + Safety {A_LOWLEV, A_STAB, A_ALTMANZ} | Asness et al. (2019) QMJ | RMW |
| B_QARP | คัดเฉพาะหุ้นที่ B_QUAL ≥ ค่ากลาง แล้วจัดอันดับด้วยเสา Value — ขนาดพอร์ต = 20% ของหุ้นที่มีทั้งสองเสา (ขั้นต่ำ 50) | "quality at a reasonable price" | (RMW+HML)/2 |
| B_FV | F-score {A_FSCORE} + Value {V_BM, V_EP, V_EBITEV, V_FCFP} | Piotroski (2000); Li & Mohanram (2019) | (RMW+HML)/2 |
| B_SHYQ | Shareholder yield {A_SHY} + Quality {Q_GPA, Q_ROIC, Q_LOWACC} | Boudoukh et al. (2007) + Novy-Marx | (HML+RMW)/2 |
| B_QVI | Quality + Value + Investment {I_LOWISS, I_LOWAG} | Fama & French (2015) 5-factor logic | (RMW+HML+CMA)/3 |

แต่ละสูตร × {overall, sector-neutral} = **12 trial** → สะสม 45 + 12 = **57**

## Grid S4 (เฉพาะผู้เข้ารอบ; นับเป็น trial)
q ∈ {10%, **20%**, 30%} (ขั้นต่ำ 50) — เพื่อนบ้าน = 10% และ 30% ในแบบการจัดอันดับเดียวกัน

## ความคาดหมาย
คาดว่า quality-heavy (B_QUAL, B_SHYQ) ดีกว่า value-heavy (B_FV) ตามผล round 001 แต่การผ่าน S3 ยาก (N = 57 และความผันผวนของผลข้ามช่วง)
