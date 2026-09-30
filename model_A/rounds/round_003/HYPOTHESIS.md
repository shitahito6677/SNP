# Round 003 — ตระกูล C: สัญญาณราคา และ พื้นฐาน × ราคา (เขียนก่อนรัน)

## คืออะไร / ทำไม
Gu, Kelly & Xiu (2020) พบว่าสัญญาณจากราคา (momentum, ความผันผวน) เป็นตัวทำนายเด่นที่สุดในหุ้นสหรัฐ; งานคลาสสิก
(Jegadeesh & Titman 1993; Ang et al. 2006; George & Hwang 2004) — และการผสม "พื้นฐาน + ราคา" อาจเสถียรกว่าอย่างใดอย่างหนึ่ง
(Asness, Moskowitz & Pedersen 2013: value + momentum ติดลบต่อกัน)

## สเปก (แน่นอน)
- **rebalance รายเดือน** (วันทำการสุดท้ายของเดือน มิ.ย. 2011 – พ.ค. 2023, 144 รอบ); U(d) ตาม PREREG_AUTORUN ณ ทุกวัน rebalance
- งบ point-in-time ณ วัน rebalance (panel รายเดือน `data/interim/panel_monthly.parquet`); ราคาจาก `lib/signals_price.py`
- top 20% (ขั้นต่ำ 50), EW, ต้นทุน 10/25 bps; **benchmark EW(U) rebalance รายเดือน**; SPY
- คะแนนผสม: percentile rank ภายใน U (หรือภายในกลุ่ม SIC แบบ sector-neutral) ของแต่ละเสา แล้วเฉลี่ยเท่ากัน (ต้องมีครบทุกเสา)

| รหัส | นิยาม | ที่มา | S5 |
|---|---|---|---|
| C_MOM | momentum 12-1 | Jegadeesh & Titman (1993) | MOM |
| C_LOWVOL | ความผันผวน 252 วันต่ำ | Ang et al. (2006) | ไม่มี proxy |
| C_TREND | ราคาเหนือเส้นเฉลี่ย 200 วัน | Han, Zhou & Zhu (2016) | ไม่มี proxy |
| C_HI52 | ใกล้จุดสูงสุด 52 สัปดาห์ | George & Hwang (2004) | MOM |
| C_QMOM | เสา Quality {Q_GPA, Q_ROIC, Q_LOWACC} + เสา {C_MOM} | Asness et al. (2013) logic | (RMW+MOM)/2 |
| C_SHYQMOM | {A_SHY} + Quality + {C_MOM} (3 เสา) | ต่อยอดตัวที่สม่ำเสมอสุดใน round 002 (ประกาศว่าเป็นการต่อยอด → นับ trial) | (HML+RMW+MOM)/3 |
| C_QLOWVOL | Quality + {C_LOWVOL} | Asness et al. (2019) quality + low risk | RMW (proxy 50%) |
| C_VMOM | Value {V_BM, V_EP, V_EBITEV, V_FCFP} + {C_MOM} | Asness, Moskowitz & Pedersen (2013) | (HML+MOM)/2 |

แต่ละตัว × {overall, sector-neutral} = **16 trial** → สะสม 57 + 16 = **73**

## Grid S4 (เฉพาะผู้เข้ารอบ)
q ∈ {10%, **20%**, 30%}; และสำหรับสัญญาณที่มี lookback: momentum lookback ∈ {6-1, **12-1**, 18-1 เดือน}, vol window ∈ {126, **252**, 504 วัน}

## ความคาดหมาย
momentum ในหุ้นใหญ่ช่วง 2017–2022 มี crash ช่วงฟื้นตัว 2020–2021 → อาจไม่ผ่าน S2; low vol มักได้ Sharpe ดีแต่ CAGR ต่ำ (อาจตก S1b)
