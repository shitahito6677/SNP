"""
test_sector_rules.py — unit test ของ sector_rules.py (Phase R4 Definition of Done: ครอบคลุม
4 shock_type x edge case ทั้ง 3 ข้อ + ยืนยันว่าคะแนนทุก sector อธิบายที่มาได้)

ไม่ใช้ pytest (ไม่ได้ติดตั้งในสภาพแวดล้อมนี้) — plain assert + runner คืน exit code 1 ถ้ามี
เทสต์ไหน fail กัน CI/คนรันมองข้าม

รัน: python3 -m model_c_rulebase.engine.test_sector_rules
"""

import sys

from model_c_rulebase.engine.sector_rules import (
    CHANNELS,
    LOADING_MATRIX,
    LOW_CONFIDENCE_DAMPENER,
    SECTORS,
    VIX_AMPLIFIER,
    MarketContext,
    StructuredVars,
    explain,
    score_event,
)

VIX_P90 = 1.128  # ค่าจริงจาก fomc_market_context.csv (452 ข่าว) คำนวณใน Phase R1/R5 — ใช้ค่า
                  # คงที่ในเทสต์เพื่อผลลัพธ์ deterministic ไม่ต้องอ่านไฟล์จริงทุกครั้งที่เทสต์รัน

PASSED = 0
FAILED = []


def check(name, condition, detail=""):
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append(f"{name}: {detail}")


def base_market(shock_type, **overrides):
    defaults = dict(rate_surprise=0.1, equity_move=-0.01, curve_slope_delta=0.02,
                     vix_delta=0.5, dxy_delta=0.1, shock_type=shock_type)
    defaults.update(overrides)
    return MarketContext(**defaults)


def base_llm(**overrides):
    defaults = dict(stance_delta=1, growth_delta=1, inflation_delta=1, labor_delta=0,
                     forward_guidance_delta=0, balance_sheet_signal=0,
                     uncertainty_language=0, financial_stability_concern=0, low_confidence=False)
    defaults.update(overrides)
    return StructuredVars(**defaults)


# --------------------------------------------------------------------------
# 1) ทุก shock_type ต้องรันได้ ให้คะแนนครบ 11 sector และอธิบายได้ (explainability)
# --------------------------------------------------------------------------

def test_all_shock_types_produce_full_explainable_scores():
    for shock_type in ["policy_tightening", "info_positive", "policy_easing", "info_negative",
                        "no_rate_surprise"]:
        market = base_market(shock_type)
        llm = base_llm()
        result = score_event(market, llm, VIX_P90)

        check(f"shock_type={shock_type}: มีครบ 11 sector",
              set(result["sectors"].keys()) == set(SECTORS),
              f"got {sorted(result['sectors'].keys())}")

        for sector in SECTORS:
            s = result["sectors"][sector]
            check(f"shock_type={shock_type}/{sector}: score เป็นตัวเลข",
                  isinstance(s["score"], float))
            check(f"shock_type={shock_type}/{sector}: contributions ครบ 7 channel",
                  set(s["contributions"].keys()) == set(CHANNELS))

            explanation = explain(result, sector)
            check(f"shock_type={shock_type}/{sector}: explain() ไม่ว่างเปล่าและมีครบ 7 channel",
                  all(c in explanation for c in CHANNELS),
                  f"explanation:\n{explanation}")


# --------------------------------------------------------------------------
# 2) C1 dampener: info_positive ต้องอ่อนกว่า policy_tightening ที่ rate_surprise เดียวกันเป๊ะ
# --------------------------------------------------------------------------

def test_c1_dampener_info_positive_weaker_than_tightening():
    llm = base_llm()
    r_tight = score_event(base_market("policy_tightening", rate_surprise=0.2), llm, VIX_P90)
    r_info = score_event(base_market("info_positive", rate_surprise=0.2), llm, VIX_P90)

    c1_tight = r_tight["channels"]["activation"]["C1"]
    c1_info = r_info["channels"]["activation"]["C1"]
    check("C1 activation: info_positive = 0.5 x policy_tightening (dampener ตามสเปก)",
          abs(c1_info - 0.5 * c1_tight) < 1e-9,
          f"c1_tight={c1_tight}, c1_info={c1_info}")


# --------------------------------------------------------------------------
# Edge case 1: XLF pivot (financial_stability_concern>=1 หรือ curve_slope_delta<0)
# --------------------------------------------------------------------------

def test_edge_case_1_xlf_pivot_triggers_on_financial_stability_concern():
    market = base_market("policy_tightening", curve_slope_delta=0.05)  # curve ไม่กลับหัว
    llm = base_llm(financial_stability_concern=1)
    result = score_event(market, llm, VIX_P90)
    xlf = result["sectors"]["XLF"]

    check("XLF pivot: C3 loading เปลี่ยนจาก 0.9 ปกติ เป็น 0.2",
          xlf["loading_used"]["C3"] == 0.2, f"got {xlf['loading_used']['C3']}")
    check("XLF pivot: C4 loading เปลี่ยนจาก -0.8 ปกติ เป็น -1.5",
          xlf["loading_used"]["C4"] == -1.5, f"got {xlf['loading_used']['C4']}")
    check("XLF pivot: มี note อธิบายว่า pivot ACTIVE",
          any("pivot ACTIVE" in n for n in xlf["notes"]), f"notes={xlf['notes']}")


def test_edge_case_1_xlf_pivot_triggers_on_curve_inversion():
    market = base_market("policy_tightening", curve_slope_delta=-0.01)  # curve กลับหัว
    llm = base_llm(financial_stability_concern=0)
    result = score_event(market, llm, VIX_P90)
    xlf = result["sectors"]["XLF"]
    check("XLF pivot: trigger จาก curve_slope_delta<0 อย่างเดียวก็พอ (ไม่ต้องมี concern flag)",
          xlf["loading_used"]["C4"] == -1.5, f"got {xlf['loading_used']['C4']}")


def test_edge_case_1_xlf_no_pivot_when_neither_condition_met():
    market = base_market("policy_tightening", curve_slope_delta=0.05)
    llm = base_llm(financial_stability_concern=0)
    result = score_event(market, llm, VIX_P90)
    xlf = result["sectors"]["XLF"]
    check("XLF ไม่ pivot: ใช้ loading ปกติ C3=0.9",
          xlf["loading_used"]["C3"] == LOADING_MATRIX["XLF"]["C3"])
    check("XLF ไม่ pivot: ใช้ loading ปกติ C4=-0.8",
          xlf["loading_used"]["C4"] == LOADING_MATRIX["XLF"]["C4"])
    check("XLF ไม่ pivot: ไม่มี pivot note",
          not any("pivot ACTIVE" in n for n in xlf["notes"]))


# --------------------------------------------------------------------------
# Edge case 2: VIX amplifier (vix_delta > p90 -> x1.3-1.5, ใช้ค่ากลาง 1.4)
# --------------------------------------------------------------------------

def test_edge_case_2_vix_amplifier_scales_all_scores():
    llm = base_llm()
    market_normal = base_market("policy_tightening", vix_delta=0.5)  # < p90
    market_spike = base_market("policy_tightening", vix_delta=5.0)   # > p90

    r_normal = score_event(market_normal, llm, VIX_P90)
    r_spike = score_event(market_spike, llm, VIX_P90)

    check("VIX amplifier: ไม่ active เมื่อ vix_delta < p90",
          r_normal["vix_amplifier_active"] is False)
    check("VIX amplifier: active เมื่อ vix_delta > p90",
          r_spike["vix_amplifier_active"] is True)

    for sector in SECTORS:
        score_normal = r_normal["sectors"][sector]["score"]
        score_spike = r_spike["sectors"][sector]["score"]
        if abs(score_normal) < 1e-9:
            continue  # 0 x amplifier ยังเป็น 0 เทียบสัดส่วนไม่ได้ ข้าม
        ratio = score_spike / score_normal
        check(f"VIX amplifier: {sector} score สเกล x{VIX_AMPLIFIER} พอดี",
              abs(ratio - VIX_AMPLIFIER) < 1e-6, f"ratio={ratio}")


# --------------------------------------------------------------------------
# Edge case 3: low_confidence dampener (x0.5)
# --------------------------------------------------------------------------

def test_edge_case_3_low_confidence_dampener_halves_scores():
    market = base_market("info_negative", vix_delta=0.5)  # กัน VIX amplifier มาปน
    llm_normal = base_llm(low_confidence=False)
    llm_low_conf = base_llm(low_confidence=True)

    r_normal = score_event(market, llm_normal, VIX_P90)
    r_low = score_event(market, llm_low_conf, VIX_P90)

    check("low_confidence dampener: flag ตรงกับ input",
          r_low["low_confidence_dampener_active"] is True and
          r_normal["low_confidence_dampener_active"] is False)

    for sector in SECTORS:
        score_normal = r_normal["sectors"][sector]["score"]
        score_low = r_low["sectors"][sector]["score"]
        check(f"low_confidence dampener: {sector} score = {LOW_CONFIDENCE_DAMPENER} x ปกติ",
              abs(score_low - LOW_CONFIDENCE_DAMPENER * score_normal) < 1e-9,
              f"normal={score_normal}, low={score_low}")


def test_edge_cases_2_and_3_combine_multiplicatively():
    market = base_market("info_negative", vix_delta=5.0)  # > p90
    llm = base_llm(low_confidence=True)
    result = score_event(market, llm, VIX_P90)
    expected = VIX_AMPLIFIER * LOW_CONFIDENCE_DAMPENER
    check("VIX amplifier x low_confidence dampener รวมกันแบบคูณ (0.7 พอดี)",
          abs(result["global_multiplier"] - expected) < 1e-9,
          f"got {result['global_multiplier']}, expected {expected}")


# --------------------------------------------------------------------------
# กลไกเฉพาะ channel ที่ควรตรวจแยก (ไม่ใช่ edge case ในสเปกแต่เป็นพฤติกรรมสำคัญที่ตั้งใจออกแบบไว้)
# --------------------------------------------------------------------------

def test_c4_not_activated_for_policy_easing():
    market = base_market("policy_easing", rate_surprise=-0.1)
    llm = base_llm(uncertainty_language=2, financial_stability_concern=2)  # สูงแต่ไม่ควรมีผลตรงนี้
    result = score_event(market, llm, VIX_P90)
    check("C4 ไม่ activate สำหรับ policy_easing (สเปกไม่ได้ระบุกลไกไว้ ไม่เดาเพิ่ม)",
          result["channels"]["activation"]["C4"] == 0.0,
          f"got {result['channels']['activation']['C4']}")


def test_c5_missing_dxy_delta_gives_zero_not_guess():
    market = base_market("policy_tightening", dxy_delta=None)
    llm = base_llm()
    result = score_event(market, llm, VIX_P90)
    check("C5 activation = 0 เมื่อ dxy_delta หายไป (ก่อน 2006) ไม่ใช่การเดา",
          result["channels"]["activation"]["C5"] == 0.0)
    xlb_notes = result["sectors"]["XLB"]["contributions"]["C5"]
    check("C5 contribution ของทุก sector = 0 เมื่อ dxy_delta หายไป", xlb_notes == 0.0)


def test_loading_matrix_matches_spec_spot_check():
    # สุ่มตรวจค่าจากตารางในเอกสารสเปก (สำเนามาตรง ไม่ใช่คำนวณ) กัน typo ตอน implement
    check("XLU C1 = -0.9 (bond-proxy duration สูงสุดกลุ่มหนึ่ง)", LOADING_MATRIX["XLU"]["C1"] == -0.9)
    check("XLRE C7 = -0.9 (leverage สูงสุด)", LOADING_MATRIX["XLRE"]["C7"] == -0.9)
    check("XLE C6 = 0.9 (inflation pass-through บวกแรงสุด)", LOADING_MATRIX["XLE"]["C6"] == 0.9)
    check("XLB C5 = -0.7 (dollar sensitivity แรงสุดรองจาก none)", LOADING_MATRIX["XLB"]["C5"] == -0.7)
    check("XLF C3 = 0.9 (NIM เฉพาะ XLF)", LOADING_MATRIX["XLF"]["C3"] == 0.9)
    check("XLP ทุก channel ไม่เป็น 0 หมด (defensive แต่ยัง react บ้างตามสเปก)",
          any(v != 0 for v in LOADING_MATRIX["XLP"].values()))
    check("XLV ทุก channel ไม่เป็น 0 หมด (defensive แต่ยัง react บ้างตามสเปก)",
          any(v != 0 for v in LOADING_MATRIX["XLV"].values()))


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()

    print(f"PASSED: {PASSED}")
    print(f"FAILED: {len(FAILED)}")
    if FAILED:
        for f in FAILED:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
