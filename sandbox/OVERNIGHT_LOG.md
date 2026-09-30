# Overnight unattended run log

โหมดนี้ไม่มีคนตอบคำถามได้ระหว่างรัน — ตามกฎที่ผู้ใช้กำหนด:
- เจอจุดต้องเลือกและไม่แน่ใจ → เลือก option ที่ risk ต่ำสุด/ย้อนกลับง่ายสุด (private ไม่ public,
  ไม่ทับไฟล์เดิม, ไม่ force push)
- เจอบั๊ก/จุดที่ปกติต้องรอ confirm → ไม่หยุดรอ, บันทึกที่นี่ว่าเจออะไร ทำไมติด แล้วข้ามไปทำ
  phase/งานอื่นที่ไม่ติดปัญหานั้นแทน
- ห้าม merge เข้า main หรือ force push — push ที่ `feature/ensemble-sandbox` เท่านั้น
- Commit แยกทุกครั้งที่ phase ใดผ่าน definition of done

Log นี้ append-only เหมือน `experiments/log.md` — ห้ามลบของเก่า

---

## เริ่ม session — 2026-09-11 (ต่อจาก Phase 0-2 ที่ commit/push ไปแล้วก่อนเข้าโหมด overnight)

Branch: `feature/ensemble-sandbox`, HEAD ก่อนเริ่ม = `28baa23` (Phase 2)
งานที่ต้องทำ: Phase 3 (manual event injection UI), Phase 4 (rule engine v1 + versioning),
Phase 5 (SQLite experiment persistence + diff) — commit แยกแต่ละ phase, verify DoD ก่อน
commit ทุกครั้ง

จะ log ความคืบหน้า/decision ที่ไม่แน่ใจ/บั๊กที่ข้ามไปก่อน ไว้ด้านล่างนี้ต่อท้ายเรื่อยๆ

---

## Phase 3 — เสร็จ, commit แล้ว

รายละเอียดเต็ม (checklist บังคับ 6 ข้อ + หลักฐาน) อยู่ใน `experiments/log.md` หัวข้อ
`sandbox_phase3_manual_event_injection` — สรุปสั้น:

- ผ่านครบ 5/6 ข้อของ checklist ด้วยหลักฐานจริง (curl, code test)
- **ข้อที่ยังไม่ครบ**: "เปิด browser เช็ค UI ไม่ error" ด้วยตาเอง — ทำไม่ได้ในโหมด unattended
  (ไม่มี browser automation tool ในสภาพแวดล้อมนี้) ทุกอย่างที่ automate ได้ (HTTP status, JS
  syntax, response schema, ไฟล์จริง) ตรวจผ่านหมดแล้ว แต่การเห็นหน้าจอจริงต้องรอผู้ใช้ตอนเช้า
  ตามที่ระบุไว้เอง — นี่ไม่ใช่บั๊กที่ต้องหยุดรอ confirm (ไม่มีอะไรผิดพลาดให้แก้) เป็นแค่ข้อ
  checklist ที่ธรรมชาติของงานทำให้ AI ทำเองไม่ได้ เลยไปต่อ Phase 4 ตามกฎ
- Design decision ที่ตัดสินใจเอง (documented ใน commit + experiments/log.md): เก็บ manual
  event เป็น CSV 1 แถวต่อ (event, ticker) แทน JSON nested — ย้อนกลับง่าย (ลบไฟล์ csv ทิ้งได้
  เฉยๆ ไม่กระทบโค้ดอื่น)

Commit: `sandbox: Phase 3 - manual event injection UI (B/C toggle, CSV, disclaimer)`

---

## Phase 4 — เสร็จ, commit แล้ว

รายละเอียดเต็มใน `experiments/log.md` หัวข้อ `sandbox_phase4_rule_engine_v1` — สรุปสั้น:

- ลบ rule engine เดิมจาก Phase 2 (`rule_table.json` + `engine.py`, weighted-sum design) แทนที่
  ด้วย versioned lookup table ตาม spec ใหม่: `sandbox/rules/rule_v1.json` (27 แถว) +
  `sandbox/engine/combine.py` (lookup ตรง, raise ถ้าไม่เจอ) + `sandbox/rules/versions.py`
  (save = สร้างไฟล์ใหม่เสมอ)
- unit test 8 case ผ่านหมด (เกิน 5 ที่กำหนด), versioning ทดสอบจริงด้วย MD5 ยืนยันว่า v1 ไม่ถูก
  แก้เลยหลัง save v2/v3
- **Decision ที่ต้อง flag ชัดเจน**: ตัวอย่าง JSON ที่ผู้ใช้แปะมาใน prompt ใช้ b/c="buy"/"sell"
  ซึ่งขัดกับ contract จริงที่ fix ไว้ตั้งแต่ Phase 1 (b/c ต้องเป็น positive/neutral/negative
  เท่านั้น) — ตัดสินใจว่าเป็น typo ในตัวอย่าง ใช้ vocabulary เดิมที่ระบบทั้งหมด (Dashboard,
  Events, Model B/C stub) พึ่งพาอยู่แทน เพราะเปลี่ยนตามตัวอย่างจะทำให้ระบบที่ทดสอบผ่านแล้วพัง
  ทันที — **ถ้าตื่นมาแล้วพบว่าตั้งใจจะให้ b/c เป็น "buy"/"sell" จริงๆ (เช่น mapping คนละแบบ)
  ต้องแก้ `sandbox/scripts/generate_rule_v1.py` ใหม่และคิดว่าจะ map ยังไงให้ตรงกับที่ Model B/C
  คืนค่าจริง** — เก็บ rule_v1.json ปัจจุบันไว้เป็น baseline เทียบได้
- ยังไม่ได้เปิด browser ดู editable UI ด้วยตาเอง (เหตุผลเดียวกับ Phase 3)

Commit: `sandbox: Phase 4 - rule engine v1 + versioning (combine(), rule_v1.json, unit tests)`

---

## Phase 5 — เสร็จ, commit แล้ว

รายละเอียดเต็มใน `experiments/log.md` หัวข้อ `sandbox_phase5_experiment_persistence` —
สรุปสั้น:

- `sandbox/experiments_db.py` (SQLite `sandbox/experiments.db`, schema ตรง spec เป๊ะทุก
  column) + หน้า Experiments เพิ่มฟอร์มรัน experiment + ตาราง saved experiments + diff
- ทดสอบจริงครบ DoD: รัน v1, แก้ rule เป็น v2 (เปลี่ยน decision ของ 1 combo), รัน v2, diff —
  เจอ diff ตรงจุดที่แก้จริง 1 คู่ (ticker,date) เป๊ะ ไม่มากไม่น้อยกว่านั้น
- Decision ที่เลือกเอง: "experiment" = รัน `combine()` เฉพาะ (ticker,date) ที่มี manual event
  ครบทั้ง B+C เท่านั้น (ข้ามคู่ที่ไม่ครบ ไม่ fabricate) — ทางเลือกอื่นที่ปฏิเสธไปเพราะขัดกับ
  "ห้ามเดา" documented ไว้ใน docstring + log

---

## สรุปรวม — จบ session overnight (Phase 0-5 ครบตาม prompt)

Commit ทั้งหมด 6 commit แยกตาม phase, push ขึ้น `feature/ensemble-sandbox` ทุกครั้ง (ไม่แตะ
main, ไม่ force push):
1. `12b8cff` Phase 0 — data validation
2. `dd10150` Phase 1 — stub interfaces
3. `28baa23` Phase 2 — Flask + Plotly dashboard
4. `07a7d71` Phase 3 — manual event injection (CSV, B/C toggle)
5. `93b53b8` Phase 4 — rule engine v1 + versioning
6. Phase 5 — SQLite experiment persistence + diff (commit นี้เอง — ดู `git log` สำหรับ hash)

**สิ่งที่ยังไม่ได้ทำ / ต้องให้พี่ตัดสินใจตอนเช้า:**
1. **เปิด browser ดู UI ด้วยตาเองทุกหน้า** — checklist บังคับข้อนี้ทำเองในโหมด unattended
   ไม่ได้เลยสักครั้ง (ไม่มี browser automation tool ในสภาพแวดล้อมนี้) ทุกอย่างที่ automate ได้
   (HTTP status, schema, MD5 diff, unit test) ตรวจผ่านหมดแล้วทุก phase แต่การเห็นหน้าจอจริง
   ยังไม่มีใครยืนยัน
2. **rule_v1.json ใช้ vocabulary "positive/neutral/negative" สำหรับ b/c** (ไม่ใช่ "buy/sell"
   ตามตัวอย่าง JSON ที่แปะมาใน prompt) — ตัดสินใจว่าตัวอย่างเป็น typo เพราะขัดกับ contract
   จริงของ Model B/C ที่ fix มาตั้งแต่ Phase 1 ถ้าไม่ใช่ typo ต้องแก้
   `sandbox/scripts/generate_rule_v1.py` ใหม่
3. **"A+B override C" priority logic** เป็น design ที่เขียนเองจาก description สั้นๆ ที่ให้มา
   ยังไม่ผ่านการ validate ใดๆ กับพฤติกรรมโมเดลจริง (เพราะยังไม่มีโมเดลจริง) — revisit ตอนมี
   Model A/B/C จริง
4. **ไม่มี Model A ในกราฟ Dashboard เลย** — Dashboard แสดงแค่ event ของ B/C (macro/company)
   เพราะ Model A ไม่ใช่ event-driven (ไม่มี headline ผูกกับมัน) ยังไม่ได้ออกแบบ UI สำหรับมัน

ไม่มีบั๊กที่ค้างแบบ "พังจริง" — ทุกจุดที่ list ไว้ข้างบนเป็น decision ที่ทำไปแล้วพร้อมเหตุผล
ไม่ใช่ของที่ทำไม่ได้แล้วข้ามเฉยๆ
