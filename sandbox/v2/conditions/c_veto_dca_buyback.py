NAME = "C-veto: ขายเมื่อ sector ติดลบ + DCA + ซื้อคืน -20%"
DESCRIPTION = ("port จาก strategy_v1 ของ sandbox v1: (1) วันที่มีเหตุการณ์ C เป็น negative ของ sector → ขายหุ้นใน sector นั้นทั้งหมด "
               "และจำราคาขาย (2) ราคาตก ≥ 20% จากจุดขาย → ซื้อคืน (3) เงินสดที่เหลือ → DCA เข้าหุ้นใน universe ที่ C positive วันนั้น "
               "(หารเท่ากัน) — ใช้ C ของวันนั้นเท่านั้น ไม่ forward-fill เหมือน v1")

BUYBACK_DROP = 0.20


def decide(ctx):
    st = ctx.state.setdefault("last_sell", {})
    w = dict(ctx.portfolio["weights"])
    cash = ctx.portfolio["cash_weight"]
    changed = False

    # 1) sell: C negative วันนี้ (ของ sector ที่ถืออยู่)
    for t in list(w):
        c = ctx.c_for(t)
        if c and c["date"] == ctx.date and c["class"] == "negative" and w[t] > 0:
            cash += w.pop(t)
            st[t] = ctx.price(t)
            ctx.note(t, f"C negative ({c['sector']}) วันนี้ → ขายทั้งหมด")
            changed = True

    # 2) buyback: ราคาตก ≥ 20% จากราคาขายล่าสุด
    buy = [t for t, p in st.items() if p and ctx.price(t) and ctx.price(t) <= p * (1 - BUYBACK_DROP)]
    if buy and cash > 1e-9:
        each = cash / len(buy)
        for t in buy:
            w[t] = w.get(t, 0.0) + each
            ctx.note(t, f"ราคา {ctx.price(t):.2f} ต่ำกว่าจุดขาย {st[t]:.2f} ≥ 20% → ซื้อคืน")
            st[t] = None
        cash = 0.0
        changed = True

    # 3) DCA เงินสดที่เหลือเข้าหุ้นที่ C positive วันนี้
    pos = [t for t in sorted(ctx.universe) if (ctx.c_for(t) or {}).get("class") == "positive"
           and ctx.c_for(t)["date"] == ctx.date]
    if pos and cash > 1e-9:
        each = cash / len(pos)
        for t in pos:
            w[t] = w.get(t, 0.0) + each
            ctx.note(t, "C positive วันนี้ → DCA เงินสดที่ว่าง")
        changed = True

    return w if changed else None
