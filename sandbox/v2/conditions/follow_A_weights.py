NAME = "ใช้น้ำหนักตามกฎของ Model A"
DESCRIPTION = "ถือหุ้นที่ผ่าน pipeline ด้วยน้ำหนักจากกฎ A (เช่น market cap ของ A2/A5, 1/vol ของ A4) แล้ว normalize ให้รวม = 1"


def decide(ctx):
    w = {}
    for t in ctx.universe:
        a = ctx.a.get(t)
        if a and a.get("weight"):
            w[t] = float(a["weight"])
    if not w:
        return {}
    s = sum(w.values())
    out = {t: v / s for t, v in w.items()}
    for t, v in out.items():
        ctx.note(t, f"น้ำหนักตามกฎ A {100 * v:.2f}%")
    return out
