"""
Smoke test — ตรวจ sandbox skeleton ทั้งชุด (stub interfaces + rule engine) แบบไม่ต้องเปิด
Flask server เพื่อยืนยันว่า reproducible จริง (input เดิม → output เดิมเสมอ) และ rule table
ครอบคลุมครบทุก combo ก่อนเอาไปใช้ต่อใน dashboard

รัน (จาก project root เพื่อให้ import `sandbox.*` เจอ): python3 -m sandbox.scripts.smoke_test
exit code 0 = ผ่านทั้งหมด, ไม่ใช่ 0 = มี assertion ไหนพัง
"""

import itertools
import sys

from sandbox import config
from sandbox.inference import model_a, model_b, model_c
from sandbox.rules import engine

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

    # 3. rule engine covers all 27 combos with no crash, and is_stub propagates
    combos_seen = set()
    for a_cls, b_cls, c_cls in itertools.product(
        ["buy", "hold", "sell"], ["positive", "neutral", "negative"], ["positive", "neutral", "negative"]
    ):
        result = engine.combine(
            {"class": a_cls, "is_stub": True},
            {"class": b_cls, "is_stub": True},
            {"class": c_cls, "is_stub": True},
        )
        combos_seen.add((a_cls, b_cls, c_cls))
        if result["signal"] not in {"BUY", "HOLD", "SELL"}:
            FAILURES.append(f"combo {(a_cls, b_cls, c_cls)} produced invalid signal {result['signal']}")
    check("rule engine handles all 27 combos without error", len(combos_seen) == 27)

    combined_real = engine.combine(a1, b1, c1)
    check("combine() propagates is_stub=True when any input is stub", combined_real["is_stub"] is True)

    combined_no_stub = engine.combine(
        {"class": "buy", "is_stub": False},
        {"class": "positive", "is_stub": False},
        {"class": "positive", "is_stub": False},
    )
    check("combine() reports is_stub=False when all inputs are non-stub", combined_no_stub["is_stub"] is False)

    # 4. config sanity (universe from Phase 0)
    check("config.TICKERS has exactly 5 tickers", len(config.TICKERS) == 5)
    for t in config.TICKERS:
        check(f"config.ticker_to_etf works for {t}", config.ticker_to_etf(t) is not None)

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
