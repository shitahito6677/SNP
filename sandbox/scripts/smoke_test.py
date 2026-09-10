"""
Smoke test — ตรวจ inference stub (Phase 1) + config (Phase 0) แบบไม่ต้องเปิด Flask server
เพื่อยืนยันว่า reproducible จริง (input เดิม → output เดิมเสมอ)

ขอบเขต: เฉพาะ stub interface + config เท่านั้น — rule engine (Phase 4) มี unit test แยกที่
`sandbox/scripts/test_combine.py` (เดิม smoke test นี้เคยรวม rule-engine check ด้วย แต่ engine
ถูกออกแบบใหม่ทั้งหมดใน Phase 4 (`sandbox/engine/combine.py`) เลยแยก test ออกจากกันชัดเจน)

รัน (จาก project root เพื่อให้ import `sandbox.*` เจอ): python3 -m sandbox.scripts.smoke_test
exit code 0 = ผ่านทั้งหมด, ไม่ใช่ 0 = มี assertion ไหนพัง
"""

import sys

from sandbox import config
from sandbox.inference import model_a, model_b, model_c

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def main():
    ticker = config.TICKERS[0]
    sector_etf = config.ticker_to_etf(ticker)  # model_c ต้องรับ ETF code เช่น "XLK" ไม่ใช่ GICS sector name

    # 1. determinism: same input -> same output, across repeated calls
    a1 = model_a.predict(ticker, "2024-01-01")
    a2 = model_a.predict(ticker, "2024-01-01")
    check("model_a.predict deterministic across calls", a1 == a2)

    b1 = model_b.predict("some headline", ticker)
    b2 = model_b.predict("some headline", ticker)
    check("model_b.predict deterministic across calls", b1 == b2)

    c1 = model_c.predict("some headline", sector_etf)
    c2 = model_c.predict("some headline", sector_etf)
    check("model_c.predict deterministic across calls", c1 == c2)

    # 2. output schema
    check("model_a output has class/score/is_stub", set(a1) >= {"class", "score", "is_stub"})
    check("model_a class in {buy,hold,sell}", a1["class"] in {"buy", "hold", "sell"})
    check("model_b class in {positive,neutral,negative}", b1["class"] in {"positive", "neutral", "negative"})
    check("model_c class in {positive,neutral,negative}", c1["class"] in {"positive", "neutral", "negative"})
    check("model_a.is_stub is True (not yet swapped)", a1["is_stub"] is True)
    check("model_b.is_stub is True (not yet swapped)", b1["is_stub"] is True)
    check("model_c.is_stub is True (not yet swapped)", c1["is_stub"] is True)
    check("model_a.IS_STUB module flag is True", model_a.IS_STUB is True)
    check("model_b.IS_STUB module flag is True", model_b.IS_STUB is True)
    check("model_c.IS_STUB module flag is True", model_c.IS_STUB is True)

    # 3. config sanity (universe from Phase 0)
    check("config.TICKERS has exactly 5 tickers", len(config.TICKERS) == 5)
    for t in config.TICKERS:
        check(f"config.ticker_to_etf works for {t}", config.ticker_to_etf(t) is not None)

    date_min, date_max = config.price_date_range()
    check("config.price_date_range returns a valid (min, max)", date_min < date_max)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
