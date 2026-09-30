"""condition สาธิตชนิด trade (Q1) — ใช้ใน tests/test_trade_causes.py และ scripts/ui_smoke.py (ไม่พึ่งข่าวของผู้ใช้)
scope 4 ตัว (AAPL, MSFT, NVDA, KR) A ปิด:
  วันแรก          ถือเท่ากัน 25%                              → BUY รอบแรก ทุกตัว
  ≥ 2022-03-01   AAPL "ข่าวร้าย" ขายครึ่ง (25% → 12.5%)       → SELL ข่าวร้าย (AAPL) + ปรับกลับเป้า (ตัวอื่น)
  ≥ 2022-03-15   MSFT รับเงินที่พักของ AAPL (25% → 37.5%)     → BUY ← รับเงินจาก AAPL
  ≥ 2022-04-01   AAPL ซื้อคืน ดึงเงินจาก MSFT (กลับ 25% ทุกตัว) → SELL → คืนให้ AAPL (MSFT) + BUY ซื้อคืน (AAPL)
"""
NAME = "สาธิตชนิด trade (Q1)"
DESCRIPTION = "ขายครึ่ง AAPL (ข่าวร้าย) → MSFT รับเงิน → AAPL ซื้อคืน ดึงเงินจาก MSFT — ใช้ทดสอบป้ายบนกราฟ"


def decide(ctx):
    st = ctx.state
    d = ctx.date
    w = {t: 0.25 for t in sorted(ctx.universe)}
    phase = 3 if d >= "2022-04-01" else 2 if d >= "2022-03-15" else 1 if d >= "2022-03-01" else 0
    first = st.get("phase") != phase
    st["phase"] = phase
    if phase == 1:
        w["AAPL"] = 0.125
        if first:
            ctx.note("AAPL", "ข่าว -2 (สาธิต) → ขายครึ่ง", kind="news_sell")
    elif phase == 2:
        w["AAPL"], w["MSFT"] = 0.125, 0.375
        if first:
            ctx.note("MSFT", "ข่าว +2 (สาธิต) → รับเงินที่พักจาก AAPL 12.50%", kind="receive", ref="AAPL")
    elif phase == 3 and first:
        ctx.note("MSFT", "ถูกดึงเงินคืน 12.50% ให้ AAPL ซื้อคืน (สาธิต)", kind="pullback", ref="AAPL")
        ctx.note("AAPL", "ราคาลง ≥ 15% (สาธิต) → ซื้อคืนเต็ม ดึงจาก MSFT", kind="buyback", ref=["MSFT"])
    return w
