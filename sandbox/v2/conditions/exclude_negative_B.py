# เดิมเคยเป็นปุ่ม "ตัด negative" ในกล่อง B ตอนนี้ย้ายมาที่นี่เพื่อความยืดหยุ่น
# (กล่อง B แค่แนบคะแนนให้ ไม่ตัดหุ้นเอง — ปรับเกณฑ์ได้เองด้านล่าง เช่น ตัดเฉพาะ -2, หรือตัดตัวที่ไม่มีข่าวด้วย)
NAME = "ตัดหุ้นที่ข่าว B ติดลบ แล้ว equal-weight"
DESCRIPTION = ("ถือทุกหุ้นใน ctx.universe ยกเว้นตัวที่ ctx.b[ticker].score < 0 (ข่าวลบ -1/-2 ณ วันนั้น) แล้วแบ่งน้ำหนักเท่ากัน · "
               "หุ้นที่ไม่มีข่าว (applicable = False) ถือไว้ตามปกติ")

CUT_BELOW = 0          # ตัดเมื่อ score < ค่านี้ (-2..+2) เช่น -1 = ตัดเฉพาะ -2
CUT_IF_NO_SIGNAL = False  # True = ตัดหุ้นที่ไม่มีข่าวด้วย (เหมือนตัวเลือก "ไม่มีสัญญาณ → ตัด" เดิม)


def decide(ctx):
    keep = []
    for t in sorted(ctx.universe):
        b = ctx.b.get(t) or {}
        if not b.get("applicable"):
            if CUT_IF_NO_SIGNAL:
                ctx.note(t, "B ไม่มีข่าว → ไม่ถือ")
                continue
            keep.append(t)
            continue
        if b.get("score") is not None and b["score"] < CUT_BELOW:
            ctx.note(t, f"B score {b['score']:+g} < {CUT_BELOW} → ไม่ถือ")
            continue
        keep.append(t)
    if not keep:
        return {}
    return {t: 1.0 / len(keep) for t in keep}
