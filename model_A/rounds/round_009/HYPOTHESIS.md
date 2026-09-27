# Round 009 — EXPLORE2 T2: factor momentum / สลับสัญญาณตามผลปีที่แล้ว (เขียนก่อนรัน)

## ที่มา
Gupta & Kelly (2019) "Factor Momentum Everywhere"; Ehsani & Linnainmaa (2022) "Factor Momentum and the Momentum Factor" —
factor ที่ได้ผลดีช่วง 12 เดือนที่ผ่านมามักได้ผลดีต่อ → ตอบโจทย์ที่สัญญาณของเราชนะแค่บางยุค (T0)

## ขั้น 1 — ข้อมูลภายนอก (ไม่นับ trial): Ken French 6 ภูมิภาค (US, Developed ex US, Europe, Japan, Asia Pacific ex Japan, Emerging) ถึง 2023-06
- factor: SMB, HML, RMW, CMA, MOM (long-short, ผลตอบแทนส่วนเกินอยู่แล้ว)
- **FMOM:** ทุกสิ้นเดือน ถือ equal-weight เฉพาะ factor ที่ผลตอบแทนสะสม 12 เดือนย้อนหลัง (t−11..t) > 0 สำหรับเดือน t+1; ถ้าไม่มีเลย = 0%
- **EQUAL:** ถือทุก factor เท่ากัน (ที่มีข้อมูลเดือนนั้น)
- รายงานต่อภูมิภาค: ค่าเฉลี่ยต่อปี, Sharpe, t-stat, ส่วนต่าง FMOM − EQUAL; ไม่มีป้าย/เกณฑ์ผ่าน (ใช้ประกอบการตีความ)

## ขั้น 2 — สัญญาณของเรา (1 trial → สะสม 119)
- สัญญาณ: Q_LOWACC (accruals ต่ำ), V_EP (earnings yield), Q_GPA (gross profitability), A_SHY (shareholder yield), C_MOM (momentum 12-1 ณ มิ.ย.)
- ทุก มิ.ย. (R): spread ของแต่ละสัญญาณ = ผลตอบแทนเฉลี่ย quintile บน − quintile ล่าง ของพอร์ตที่จัด ณ มิ.ย. ปีก่อน (R−1) ถือถึง R
  (ใช้เฉพาะข้อมูลที่รู้ผล ณ R; universe U(R−1); หุ้นที่หยุดซื้อขาย = เงินสด)
- เลือกเฉพาะสัญญาณที่ spread > 0 → คะแนน = ค่าเฉลี่ย percentile rank (overall) → top 20% (ขั้นต่ำ 50), EW, rebalance มิ.ย.
- ถ้าไม่มีสัญญาณใดเป็นบวก หรือเป็นรอบแรก (มิ.ย. 2011, ยังไม่มีปีก่อน) → ถือ EW(U) (กระทบเฉพาะช่วงประกอบ)
- trial_id: `r009_FMOM_SIGNALS`; S5 proxy = ค่าเฉลี่ยของ factor ที่เกี่ยวข้อง (RMW, HML, MOM) → ใช้ตามตาราง PREREG_AUTORUN (composite)

## Grid S4 (เฉพาะผู้เข้ารอบ): lookback spread ∈ {6, 12, 24 เดือน}; q ∈ {10, 20, 30%}
## ความคาดหมาย: ขั้น 1 น่าจะเป็นบวกในหลายภูมิภาคตามงานต้นฉบับ; ขั้น 2 มีแค่ 5 สัญญาณและ 11 ครั้งตัดสิน → เสียงรบกวนสูง
