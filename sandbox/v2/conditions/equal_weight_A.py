NAME = "Equal-weight ทุกตัวที่ผ่าน pipeline"
DESCRIPTION = "ถือทุกหุ้นใน ctx.universe (หุ้นที่ผ่านกล่องที่เปิดอยู่ทั้งหมด) น้ำหนักเท่ากัน — ปรับพอร์ตเฉพาะวันที่รายชื่อเปลี่ยน"


def decide(ctx):
    names = sorted(ctx.universe)
    if not names:
        return {}
    w = 1.0 / len(names)
    return {t: w for t in names}
