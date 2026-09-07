# SP — Multi-Model Stock Investment System (S&P500)

## ภาพรวม

โปรเจคนี้เป็นระบบช่วยตัดสินใจลงทุนหุ้นในดัชนี S&P 500 โดยผสานผลลัพธ์จาก 3 โมเดลที่มองปัญหาคนละมุม:

- **Model A — Piotroski Fundamental Screening**
  ให้คะแนนความแข็งแรงทางการเงินของบริษัทด้วย Piotroski F-Score (งบการเงิน/fundamental data)

- **Model B — FinBERT Company News Sentiment**
  วิเคราะห์ sentiment จากข่าวรายบริษัทด้วย FinBERT เพื่อจับมุมมองตลาดต่อหุ้นแต่ละตัว

- **Model C — Macro/FOMC News → Qwen → FinBERT → XGBoost (per GICS sector)**
  pipeline วิเคราะห์ข่าวมหภาค/FOMC: ใช้ Qwen ประมวลผล/สรุปข่าว → ส่งต่อ FinBERT ทำ sentiment
  → XGBoost ทำนายผลกระทบ โดยแยกโมเดลตาม 11 GICS sector

ผลลัพธ์จากทั้ง 3 โมเดลจะถูกผสาน (ensemble) เพื่อสนับสนุนการตัดสินใจลงทุนในระดับหุ้นรายตัวและระดับ sector

## สถานะปัจจุบัน

กำลังเริ่มต้นโปรเจคใหม่ทั้งหมด (rebuild from scratch) ยังไม่มี pipeline ใดที่สมบูรณ์

## หลักการทำงานที่ต้องยึดถือ

- **เน้นความเป็นระบบ**: โครงสร้างโค้ด, ข้อมูล, และ experiment ต้องจัดระเบียบ ทำซ้ำได้ (reproducible)
- **ห้ามเดาผลลัพธ์**: ทุก claim เกี่ยวกับผลลัพธ์ของโมเดล/ข้อมูล ต้อง validate ด้วยการรันโค้ดจริงเสมอ
  ห้ามสรุปหรือคาดเดาตัวเลข/performance โดยไม่มีการรันจริงมายืนยัน
- ก่อนเริ่มงานส่วนใดของแต่ละโมเดล ควรตรวจสอบ/ทดสอบ data pipeline ให้ถูกต้องก่อนต่อยอด

## โครงสร้างโฟลเดอร์

- `data/` — ข้อมูลดิบและข้อมูลที่ผ่านการประมวลผล (fundamental data, news, sector mapping ฯลฯ)
- `notebooks/` — Jupyter notebooks สำหรับ exploration, prototyping, และวิเคราะห์ผลลัพธ์
- `src/` — โค้ด production/reusable (data loaders, feature engineering, model training, pipeline สำหรับแต่ละ Model A/B/C)
- `experiments/` — บันทึกการทดลอง, ผลการรัน, เปรียบเทียบ config/hyperparameter ต่างๆ
