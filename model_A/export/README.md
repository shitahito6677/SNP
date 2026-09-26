# Export / adapter สำหรับ web test simulator (`sandbox/`)

**ยังไม่มี adapter** — AUTORUN ข้อ 7 กำหนดให้ทำ adapter "ของกฎที่ freeze แล้วเท่านั้น" และ ณ ตอนนี้ไม่มีกฎใดผ่านเกณฑ์ถึงขั้น freeze
(ดู `../REPORT.md`) การส่งกฎที่ไม่ผ่านเกณฑ์เข้า simulator จะทำให้เข้าใจผิดว่าเป็นโมเดลที่ใช้ได้

สเปกที่ adapter ต้องทำเมื่อมีกฎ freeze (อ่านจาก `sandbox/inference/model_a.py` และ `sandbox/inference/README.md`):
- `predict(ticker: str, date: str) -> dict` คง key เดิม `class` ("buy"|"hold"|"sell"), `score` ([0, 1]), `is_stub` (False)
- เพิ่ม key: `score_0_100`, `signal`, `reasons` (เหตุผลรายกฎ), `model_version`, `applicable` (False + hold สำหรับกลุ่มการเงินถ้ากฎไม่ครอบคลุม)
- คะแนนต่อหุ้นต่อวันคำนวณล่วงหน้าเก็บเป็นไฟล์ในโฟลเดอร์นี้; ห้ามแก้ไฟล์ใน `sandbox/` จนกว่าผู้ใช้อนุมัติ
