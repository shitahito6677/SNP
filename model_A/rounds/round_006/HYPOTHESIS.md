# Round 006 — ตระกูล F: ML เป็น baseline เทียบ (เขียนก่อนรัน)

## คืออะไร / ทำไม
ใช้ ML (Gu, Kelly & Xiu 2020) เป็น "เพดาน" ว่าข้อมูลชุดนี้บีบผลตอบแทนส่วนเกินได้แค่ไหน เทียบกับกฎง่าย ๆ — ผลสุดท้ายต้องเป็นกฎที่อธิบายได้
จึงสกัดกฎจาก tree ตื้น ๆ ด้วย

## สเปก (แน่นอน)
- feature 19 ตัว: Q_GPA, Q_ROIC, Q_LOWACC, V_BM, V_EP, V_EBITEV, V_FCFP, I_LOWISS, I_LOWAG, A_FSCORE, A_GSCORE, A_ALTMANZ, A_SHY,
  A_STAB, A_LOWLEV, C_MOM, C_LOWVOL, C_TREND, C_HI52 → แปลงเป็น percentile rank ภายใน U ต่อเดือน, ไม่มีค่า = 0.5
- label: ผลตอบแทน 12 เดือนข้างหน้า (Adj Close, หุ้นที่ราคาหยุด = เงินสด) แปลงเป็น percentile rank ภายในเดือน
- rebalance รายปี (มิ.ย. 2011–2022), top 20% ตามคะแนนทำนาย (ขั้นต่ำ 50), EW, 10/25 bps; benchmark EW(U) รายปี
- **walk-forward (expanding):** ณ วัน rebalance R เทรนด้วยแถวรายเดือนที่ R_row + 12 เดือน ≤ R (label รู้ผลแล้ว) เท่านั้น
  ต้องมี ≥ 12 เดือนของข้อมูลเทรน → โมเดลเริ่ม มิ.ย. 2013; รอบ มิ.ย. 2011–2012 ถือ EW(U) (กระทบเฉพาะช่วงประกอบ)
- โมเดล (ค่าตายตัว ไม่จูน):
  - F_GBM: `HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, random_state=42)`
  - F_TREE2: `DecisionTreeRegressor(max_depth=2, min_samples_leaf=200, random_state=42)` → กฎ = เงื่อนไขของใบ (leaf);
    เลือกหุ้นจากใบที่ค่าทำนายสูงสุดลงมาจนครบจำนวน; ใบสุดท้ายที่ใช้ไม่หมดเรียงตามชื่อ yahoo ticker (ประกาศล่วงหน้า)
- **2 trial** → สะสม 91 + 2 = **93**
- S5: ML ไม่มี proxy อิสระ → ตก S5 โดยอัตโนมัติ (ได้สูงสุดระดับ B)

## Grid S4 (เฉพาะผู้เข้ารอบ)
q ∈ {10%, 20%, 30%}; GBM max_depth ∈ {2, **3**, 4}; tree max_depth ∈ {1, **2**, 3}

## ความคาดหมาย
ข้อมูลไม่มาก (12 ปี, ~300 หุ้น) → ML อาจไม่ดีกว่ากฎง่าย; ถ้า ML ก็ไม่ผ่าน S1 แปลว่าสัญญาณในข้อมูลนี้อ่อนจริง
