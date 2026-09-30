NAME = "ตัดหุ้นที่ข่าว B ติดลบ แล้ว equal-weight"
DESCRIPTION = "จาก ctx.universe ตัดตัวที่ B ล่าสุดเป็น negative (ภายในอายุสัญญาณ) ออก แล้วถือที่เหลือเท่า ๆ กัน"


def decide(ctx):
    keep = []
    for t in sorted(ctx.universe):
        b = ctx.b.get(t)
        if b and b.get("class") == "negative":
            ctx.note(t, "B negative → ไม่ถือ")
            continue
        keep.append(t)
    if not keep:
        return {}
    return {t: 1.0 / len(keep) for t in keep}
