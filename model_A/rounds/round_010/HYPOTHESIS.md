# Round 010 — EXPLORE2 T5: value + momentum + quality แบบเรียบง่าย (เขียนก่อนรัน)
- ที่มา: Asness, Moskowitz & Pedersen (2013) "Value and Momentum Everywhere" — value กับ momentum สัมพันธ์ติดลบ การรวมจึงนิ่งกว่า; quality (accruals, Sloan 1996)
- สเปกเดียว (ห้ามจูน): คะแนน = ค่าเฉลี่ยเท่ากันของ percentile ภายในกลุ่ม SIC ของ Q_LOWACC (accruals ต่ำ), V_EP (earnings yield), C_MOM (12-1)
  ต้องมีครบทั้ง 3; top 20% (ขั้นต่ำ 50), EW; benchmark EW(U) ความถี่เดียวกัน; ต้นทุน 10/25 bps
- 2 trial: `r010_VMQ_sector_A` (rebalance มิ.ย.), `r010_VMQ_sector_Q` (รายไตรมาส) → สะสม 121
- ตรวจความซ้ำ: ไม่ซ้ำกับ C_QMOM (เสา quality 3 ตัว + mom), C_VMOM (เสา value 4 ตัว + mom), C_SHYQMOM (SHY + quality + mom) — จึงไม่ข้าม
- S5 proxy: (RMW + HML + MOM)/3; grid S4 (เฉพาะผู้เข้ารอบ): q ∈ {10, 20, 30%}, ความถี่ M–Q–S–A
- ความคาดหมาย: value (E/P) ถ่วงผลในช่วง 2017–2022 (round 001–003) → ไม่น่าผ่าน S1
