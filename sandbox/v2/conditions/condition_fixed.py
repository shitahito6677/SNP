NAME = "คัดหุ้นรายปี หลบข่าวร้าย ย้ายไปข่าวดี (fixed)"
DESCRIPTION = (
    "ทุก มิ.ย. ซื้อหุ้นที่ Model A เลือก น้ำหนักเท่ากัน · "
    "ข่าว -2 ขายครึ่งทันที · ข่าว -1 รอราคาหลุดเส้นค่าเฉลี่ยก่อนค่อยขายครึ่ง · "
    "เงินที่ได้ย้ายไปหุ้นข่าว +2 (ถ้ายังไม่มีให้ถือเงินสดรอ) · "
    "ถ้าหุ้นที่ขายไปลงต่ออีก 15% ดึงเงินกลับมาซื้อคืนเต็มจำนวน · ข่าวบวกอื่น ๆ ไม่ทำอะไร"
)

# ===== แก้ไข (human err) จากที่เจอในเว็บจริง =====
# 1) เดิม: ตรวจ "t in cut" เฉยๆ ทำให้หุ้นที่เคยขายครึ่งแล้วถูกซื้อคืนเต็ม (done=True)
#    ถูกกันออกจากระบบตรวจข่าวไปตลอดทั้งปี (ทั้งที่ตอนนี้ถือเต็มพอร์ตเหมือนเดิมแล้ว)
#    -> เปลี่ยนเป็นเช็ค "กำลังอยู่ในสถานะขายครึ่งค้างอยู่" (_is_reduced) แทน เพื่อให้กลับมา
#       ถูกตรวจข่าวใหม่ได้อีกหลังซื้อคืนเต็มแล้ว (แก้ทั้งจุดตรวจข่าวร้าย และจุดเป็นปลายทางรับเงินข่าวดี)
# 2) เดิม: pending (ข่าว -1 รอยืนยัน) เช็ค "t in cut" ตรงๆ ซึ่งพอเจอบั๊กข้อ 1 ก็พาลผิดตามไปด้วย
#    (หุ้นที่เคย cut มาก่อนจะไม่มีทาง pending ได้อีกเลย) -> แก้ให้ใช้ _is_reduced เหมือนกัน
# 3) เดิม: _news() ดึงค่าจาก ctx.b[t] เฉพาะ key "class"/"cls"/"label" และต้องเป็นตัวเลข -2..2
#    เท่านั้น ถ้า B ส่ง field ตัวเลขจริงมาอยู่ใน key ชื่ออื่น (เช่น raw_label/score/value) หรือ
#    "class" ดันเป็นข้อความหมวด (เช่น "negative") จะแปลงเลขไม่ได้แล้วคืน None เงียบ ๆ ทำให้
#    เจอข่าว -2 แล้วไม่ขายทั้งที่กราฟ/B โชว์ข่าวถูกต้อง -> เพิ่ม key ที่ลองอ่านให้ครอบคลุมขึ้น +
#    เพิ่ม fallback แปลงข้อความหมวดเป็นตัวเลข + เช็ค applicable:false ให้ชัดเจนก่อนเสมอ

# 4) (N0 — ยืนยันจากการรันจริง) แก้ข้อ 3 ยังไม่พอ: ลำดับ key ที่ลองอ่านเจอ "class" ก่อน "label"/"score"
#    record ของ B มีทั้ง class = "negative" (ข้อความ 3 ระดับ) และ label = -2 / score = -2.0 (ตัวเลข 5 ระดับ)
#    → _news() อ่านได้ "negative" แล้วแปลงเป็น -1 เสมอ: ข่าว -2 ไม่เคยถูกขายครึ่งทันที และข่าว +2 ไม่เคยรับเงิน
#    (หลักฐาน: debug/N0_evidence.md — label 2 → _news=1, label -2 → _news=-1)
#    -> อ่านตัวเลข "label" / "score" (สัญญา B: -2..+2) ก่อนเสมอ ค่อยถอยไปอ่านข้อความหมวด
# 5) (N5) เพิ่ม ctx.note(...) ทุกทางแยกของ decide() ให้หน้าหุ้นรายตัวบอกได้ว่าวันนั้นทำ/ไม่ทำเพราะอะไร — ไม่เปลี่ยนน้ำหนัก
# 6) (Q1) ctx.note แนบชนิดของ trade (kind/ref) ให้กราฟแยกป้าย SELL ข่าวร้าย / SELL ดึงเงินคืน / BUY รับเงิน / BUY ซื้อคืน
#    + note บนหุ้นที่ถูกดึงเงินคืน (เดิมมี note แค่ที่หุ้นที่ซื้อคืน) + note ข่าว +2 ไม่บอกว่า "ไม่ทำอะไร" แล้ว (อาจรับเงินในขั้นที่ 4)
#    — ไม่เปลี่ยนน้ำหนักที่คืน (test: tests/test_trade_causes.py เทียบกับผลก่อนแก้)
# 7) (Q2) MA_DAYS / MA_TYPE ปรับได้จากหน้าเว็บ (PARAMS) + เลือก EMA ได้ — ค่าเริ่มต้น SMA50 = คำนวณเหมือนเดิมทุกบรรทัด
# ไฟล์นี้ = equal_weight_A_v2_v2_v2.py ของผู้ใช้ (backup: sandbox/v2/backups/20260929-142129/) + แก้ข้อ 4–7 เท่านั้น

# ===== ค่าที่ปรับได้ =====
SELL_FRACTION = 0.5   # ขายกี่ส่วนเมื่อเจอข่าวร้าย
MA_DAYS = 50          # เส้นค่าเฉลี่ยกี่วันที่ใช้ยืนยันข่าว -1 (ปรับได้จากหน้าเว็บ — ดู PARAMS)
MA_TYPE = "SMA"       # SMA = ค่าเฉลี่ยธรรมดา · EMA = ถ่วงน้ำหนักราคาล่าสุดมากกว่า (ไวกว่า)
PENDING_DAYS = 20     # ข่าว -1 รอยืนยันได้กี่วันทำการ ก่อนยกเลิก
DIP_PCT = 0.15        # ลงต่อกี่ % จากราคาที่ขาย ถึงจะซื้อคืน
STRONG_BAD, BAD, STRONG_GOOD = -2, -1, 2

# ค่าที่ปรับได้จากหน้าเว็บ (ต้องเป็นตัวอักษรล้วน — ระบบอ่านด้วย ast ไม่รันโค้ด) · ค่าที่ตั้งจะแทน MA_DAYS / MA_TYPE ข้างบนตอนรัน
PARAMS = {
    "MA_DAYS": {"type": "int", "default": 50, "min": 5, "max": 250, "label": "เส้นค่าเฉลี่ยยืนยันข่าว -1 (วัน)",
                "help": ("ใช้แค่จังหวะยืนยันข่าว -1 เท่านั้น: หลังข่าว -1 ระบบรอดูว่าราคาปิดหลุดต่ำกว่าเส้นค่าเฉลี่ยนี้ภายใน 20 วันทำการไหม ถ้าหลุดจึงขายครึ่ง · "
                        "ไม่มีผลกับ SELL ข่าว -2, SELL → คืนให้ (ถูกดึงเงินคืนเมื่อหุ้นอื่นซื้อคืน), BUY รับเงินจากข่าว +2, rebalance รายปี หรือการปรับกลับเป้า"
                         " · ต้องมีราคาย้อนหลังพอ (SMA ≥ 80% ของจำนวนวัน, EMA ≥ จำนวนวัน) — ช่วงต้นการทดสอบมี warm-up 90 วันทำการ ถ้าตั้งเกินนั้นข่าว -1 ช่วงแรกจะยืนยันไม่ได้")},
    "MA_TYPE": {"type": "choice", "default": "SMA", "choices": ["SMA", "EMA"], "label": "ชนิดเส้นค่าเฉลี่ย",
                "help": ("SMA = ค่าเฉลี่ยธรรมดา N วัน · EMA = ค่าเฉลี่ยถ่วงน้ำหนักราคาล่าสุดมากกว่า (ไวกว่า; k = 2/(N+1) เริ่มจาก SMA ของ N วันแรกในช่วง 3N วัน) · "
                         "ใช้แค่จังหวะยืนยันข่าว -1 เท่านั้น เหมือนจำนวนวันด้านบน — ไม่มีผลกับ SELL → คืนให้ หรือ trade ชนิดอื่น")},
}

_MEM = {}  # สำรอง ถ้า ctx.state ไม่ใช่ dict

# หมวดข้อความ -> ตัวเลข -2..2 (เผื่อ B ส่งมาเป็นข้อความแทนตัวเลขดิบ)
_CATEGORY_MAP = {
    "strong_negative": -2, "very_negative": -2, "strongly_negative": -2,
    "negative": -1, "bad": -1,
    "neutral": 0, "none": 0, "no_impact": 0,
    "positive": 1, "good": 1,
    "strong_positive": 2, "very_positive": 2, "strongly_positive": 2,
}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _news(ctx, t):
    """คลาสข่าวจาก Model B เป็น -2..+2 หรือ None ถ้าไม่มีข่าว/อ่านค่าไม่ได้"""
    try:
        v = ctx.b[t]
    except (KeyError, TypeError, IndexError):
        return None

    if isinstance(v, dict):
        if v.get("applicable") is False:
            return None
        # ลองอ่านตัวเลขดิบก่อน แล้วค่อยลอง field ที่อาจเป็นข้อความหมวดทีหลัง
        candidates = (
            "label", "score",  # ตัวเลข -2..+2 ตามสัญญา B — ต้องมาก่อน "class" (ข้อความ 3 ระดับ) เสมอ
            "raw_class", "raw_label", "label_value", "value", "score_raw",
            "class", "cls", "sentiment_class", "bucket",
        )
        found = None
        for k in candidates:
            if v.get(k) is not None:
                found = v[k]
                break
        v = found

    if isinstance(v, str):
        key = v.strip().lower().replace(" ", "_")
        if key in _CATEGORY_MAP:
            return _CATEGORY_MAP[key]

    n = _num(v)
    if n is None or not -2 <= n <= 2:
        return None
    return int(round(n))


def _price(ctx, t):
    try:
        return _num(ctx.price(t))
    except Exception:
        return None


def _ma(ctx, t, n):
    """ค่าเฉลี่ยราคาปิด n วันล่าสุด (SMA) หรือ EMA n วัน ตาม MA_TYPE"""
    try:
        h = ctx.history(t, n if MA_TYPE == "SMA" else 3 * n)
    except Exception:
        return None
    if hasattr(h, "columns"):
        col = next((c for c in h.columns if str(c).lower() in ("close", "adj_close", "adj close")), None)
        if col is None:
            return None
        h = h[col]
    try:
        vals = [float(x) for x in (h.values if hasattr(h, "values") else h)]
    except Exception:
        return None
    vals = [x for x in vals if x == x]  # ตัด NaN
    if MA_TYPE == "EMA":
        if len(vals) < n:
            return None
        k, e = 2 / (n + 1), sum(vals[:n]) / n
        for x in vals[n:]:
            e = x * k + e * (1 - k)
        return e
    return sum(vals) / len(vals) if len(vals) >= int(n * 0.8) else None


def _is_reduced(cut, t):
    """t กำลังอยู่ในสถานะ 'ขายครึ่งไปแล้ว ยังไม่ได้ซื้อคืนเต็ม' อยู่หรือไม่"""
    rec = cut.get(t)
    return bool(rec) and not rec["done"]


def _cut(ctx, st, t):
    """ขายหุ้น t ตามสัดส่วน SELL_FRACTION เงินที่ได้พักเป็นเงินสดก่อน"""
    w = st["w"]
    p = _price(ctx, t)
    if p is None or w.get(t, 0) <= 0:
        return
    amt = w[t] * SELL_FRACTION
    w[t] -= amt
    st["cut"][t] = {"price": p, "amt": amt, "moved": {"_cash": amt}, "done": False}


def decide(ctx):
    st = ctx.state if isinstance(getattr(ctx, "state", None), dict) else _MEM
    names = sorted(ctx.universe)
    if not names:
        return {}

    # 1) รายชื่อจาก Model A เปลี่ยน (รอบ มิ.ย.) → เริ่มปีใหม่ ถือเท่ากันทุกตัว
    if st.get("list") != names:
        st["list"] = names
        st["w"] = {t: 1.0 / len(names) for t in names}
        st["cut"] = {}      # ประวัติหุ้นที่เคยขายครึ่ง (เก็บไว้ตลอด แม้ done=True แล้ว)
        st["pending"] = {}  # หุ้นข่าว -1 ที่รอหลุดเส้นค่าเฉลี่ย
    w, cut, pending = st["w"], st["cut"], st["pending"]

    # 2) ตรวจข่าวของหุ้นในพอร์ต
    #    ข้าม เฉพาะหุ้นที่ "กำลังขายครึ่งค้างอยู่" (_is_reduced) เท่านั้น
    #    หุ้นที่เคยขายครึ่งแล้วถูกซื้อคืนเต็ม (done=True) ต้องกลับมาตรวจข่าวใหม่ได้
    for t in names:
        if _is_reduced(cut, t):
            ctx.note(t, f"ข้ามการตรวจข่าว: อยู่ในสถานะขายครึ่งค้างอยู่ (_is_reduced=True) — รอราคาลงอีก {DIP_PCT:.0%} จากจุดขายเพื่อซื้อคืนเต็ม")
            continue
        c = _news(ctx, t)
        if c is not None and c <= STRONG_BAD:
            pending.pop(t, None)
            ctx.note(t, f"ข่าว {c:+d} → ขายครึ่งทันที (เงินพักเป็นเงินสด รอหุ้นข่าว +2)", kind="news_sell")
            _cut(ctx, st, t)
        elif c == BAD and t not in pending:
            ctx.note(t, f"ข่าว -1 → รอยืนยันด้วยราคาหลุดเส้น {MA_TYPE}{MA_DAYS} ภายใน {PENDING_DAYS} วันทำการ")
            pending[t] = PENDING_DAYS
        elif c == STRONG_GOOD:
            ctx.note(t, "ข่าว +2 → ไม่ขาย · เป็นปลายทางรับเงินที่พักจากการขายครึ่ง (ถ้ามีเงินพักอยู่)")
        elif c is not None:
            ctx.note(t, f"ข่าว {c:+d} → ไม่ทำอะไร (กฎนี้ทำเฉพาะ -2 / -1 / +2)")
        # ข่าวบวก: ไม่ทำอะไร

    # 3) ข่าว -1: ขายเมื่อราคาหลุดเส้นค่าเฉลี่ย ถ้ารอนานเกินกำหนดให้ยกเลิก
    for t in list(pending):
        if _is_reduced(cut, t):
            pending.pop(t)
            continue
        p, ma = _price(ctx, t), _ma(ctx, t, MA_DAYS)
        if p is not None and ma is not None and p < ma:
            pending.pop(t)
            ctx.note(t, f"ข่าว -1 ยืนยันแล้ว: ราคา {p:.2f} < {MA_TYPE}{MA_DAYS} {ma:.2f} → ขายครึ่ง", kind="news_sell")
            _cut(ctx, st, t)
        else:
            pending[t] -= 1
            ctx.note(t, f"รอยืนยันข่าว -1: ราคา {p} ยังไม่หลุด {MA_TYPE}{MA_DAYS} ({ma}) · เหลือ {max(pending[t], 0)} วันทำการ"
                        if pending[t] > 0 else "ครบกำหนดรอยืนยันข่าว -1 แล้ว ราคาไม่หลุด MA → ยกเลิก ไม่ขาย")
            if pending[t] <= 0:
                pending.pop(t)

    # 4) เงินสดที่พักไว้ → ย้ายไปหุ้นที่มีข่าว +2 (แบ่งเท่ากัน)
    #    ปลายทางต้องไม่ใช่หุ้นที่กำลังขายครึ่งค้างอยู่ (แต่ถ้าซื้อคืนเต็มแล้วรับเงินได้ตามปกติ)
    good = [x for x in names if not _is_reduced(cut, x) and _news(ctx, x) == STRONG_GOOD]
    if good:
        for src, rec in cut.items():
            cash = rec["moved"].pop("_cash", 0.0)
            if cash > 0:
                each = cash / len(good)
                for g in good:
                    w[g] = w.get(g, 0.0) + each
                    rec["moved"][g] = rec["moved"].get(g, 0.0) + each
                    ctx.note(g, f"ข่าว +2 → รับเงินที่พักจากการขายครึ่งของ {src} {each:.2%} ของพอร์ต", kind="receive", ref=src)

    # 5) หุ้นที่ขายไปลงต่อถึง DIP_PCT และยังอยู่ในรายชื่อ → ดึงเงินกลับมาซื้อคืนเต็มจำนวน
    for t, rec in cut.items():
        if rec["done"] or t not in names:
            continue
        p = _price(ctx, t)
        if p is not None and p <= rec["price"] * (1 - DIP_PCT):
            for g, a in rec["moved"].items():
                if g != "_cash":
                    w[g] = max(0.0, w.get(g, 0.0) - a)
                    ctx.note(g, f"ถูกดึงเงินคืน {a:.2%} ของพอร์ต ให้ {t} ซื้อคืนเต็ม (ราคา {t} ลง ≥ {DIP_PCT:.0%} จากจุดขาย)", kind="pullback", ref=t)
            pulled = sorted(g for g in rec["moved"] if g != "_cash")
            w[t] = w.get(t, 0.0) + rec["amt"]
            rec["moved"] = {}
            rec["done"] = True
            ctx.note(t, f"ราคา {p:.2f} ลง ≥ {DIP_PCT:.0%} จากจุดขาย {rec['price']:.2f} → ดึงเงินกลับมาซื้อคืนเต็มจำนวน"
                        + (f" (ดึงจาก {', '.join(pulled)})" if pulled else " (จากเงินสดที่พักไว้)"), kind="buyback", ref=pulled)

    # น้ำหนักรวมอาจน้อยกว่า 1 = ส่วนที่เหลือถือเป็นเงินสด
    return {t: v for t, v in w.items() if v > 1e-9}