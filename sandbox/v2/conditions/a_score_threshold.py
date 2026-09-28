# เดิมเคยเป็นช่อง "score ≥" ในกล่อง A ตอนนี้ย้ายมาที่นี่เพื่อความยืดหยุ่น
# (กล่อง A ส่งมาแค่หุ้นที่กฎของ version นั้นเลือก — class selected + applicable — ถ้าต้องการคัดเข้มขึ้นด้วย score ให้ทำที่นี่)
# ⚠️ ความหมาย/สเกลของ score ต่างกันตามกฎของ A (ดู score_meaning ใน manifest ของ version) บางกฎไม่มี score → ข้ามตัวนั้น
NAME = "ถือเฉพาะหุ้นที่ A score ≥ เกณฑ์ (equal-weight)"
DESCRIPTION = "จาก ctx.universe ถือเฉพาะตัวที่ ctx.a[ticker].score ≥ MIN_SCORE แบ่งน้ำหนักเท่ากัน — ตัวที่ไม่มี score ไม่ถือ"

MIN_SCORE = 90.0  # A1–A5: percentile 0–100 ของทั้ง universe (สูง = ดี)


def decide(ctx):
    keep = []
    for t in sorted(ctx.universe):
        a = ctx.a.get(t) or {}
        sc = a.get("score")
        if sc is None:
            ctx.note(t, "A ไม่มี score → ไม่ถือ")
            continue
        if sc >= MIN_SCORE:
            keep.append(t)
    if not keep:
        return {}
    for t in keep:
        ctx.note(t, f"A score {ctx.a[t]['score']:.1f} ≥ {MIN_SCORE:g}")
    return {t: 1.0 / len(keep) for t in keep}
