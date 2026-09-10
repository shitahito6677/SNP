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
