"""
sector_rules.py — ชั้น 3 ของ Model C rule-based sector impact engine: sector loading matrix
× channel activation ตัดสิน sector_impact_score จาก shock_type (R2) + structured variables
ที่ LLM สกัดมา (R3) + market data ดิบ (R1)

**หลักการออกแบบที่ต้องยึด:** LLM (R3) ไม่เคยพูดถึง sector เลย — engine นี้เป็นจุดเดียวที่ตัดสิน
ผลต่อ sector ทั้งหมด ด้วยกลไกทางการเงินที่มีทฤษฎีรองรับ (ดู docstring ของแต่ละ channel)
ไม่ใช่ black box — ทุกฟังก์ชัน `score_event()` คืนคำอธิบายเสมอว่าคะแนนมาจาก channel ไหนเท่าไหร่
(explainability คือจุดขายหลักของแนวทางนี้ ตามที่กำหนดไว้ ต้องมาก่อน accuracy)

**สิ่งสำคัญที่ต้องแยกให้ชัด (ประกาศไว้ตรงนี้ครั้งเดียว ไม่ต้องพูดซ้ำทุกจุด):**
    - LOADING_MATRIX ทั้งหมดคือ**ค่าจากทฤษฎี** (ตามสเปกที่กำหนดไว้ในเอกสารออกแบบ) **ห้ามถือเป็น
      ค่าจริง** ต้อง calibrate ด้วยข้อมูลจริงใน Phase R6 ถ้า R5 พิสูจน์ว่ามีสัญญาณจริงก่อน
    - ค่าคงที่ตัวคูณ/amplifier ในฟังก์ชัน `compute_channel_activations()` (เช่น 1.5, 0.5, 0.3,
      1.3-1.5 ของ VIX amplifier) เป็นค่าที่**ตีความเองจากคำอธิบายเชิงคุณภาพ**ในสเปก (ลูกศร
      ขึ้น/ลง + คำอธิบายวงเล็บ) เพราะสเปกให้แค่ทิศทาง/น้ำหนักเชิงคุณภาพ ไม่ได้ให้สูตรตัวเลขตรงๆ —
      เป็นจุดที่ต้อง calibrate ใน R6 เช่นเดียวกับ loading matrix ไม่ใช่ค่าที่พิสูจน์แล้ว

ทฤษฎีอ้างอิง (ตรงกับที่ระบุในเอกสารออกแบบ exp_03):
    1. Bernanke & Kuttner (2005, JF) — unexpected rate cut 25bp ~ +1% broad equity index,
       อุตสาหกรรมต่างกันตอบสนองไม่เท่ากัน (พื้นฐานของแนวคิด sector loading ที่ต่างกัน)
    2. Gürkaynak, Sack & Swanson (2005) — target factor (ระดับดอกเบี้ยปัจจุบัน) กับ path factor
       (forward guidance) ต้องแยกกัน — สะท้อนใน C1 ใช้ rate_surprise, C3 ใช้ curve_slope_delta
    3. Nakamura & Steinsson (2018), Campbell et al. (2012) — Fed information effect
       (Delphic vs Odyssean) — สะท้อนใน shock classification 2x2 จาก R2 และ C2 amplification
       สำหรับ info_positive/info_negative
    4. Jarociński & Karadi (2020) — sign restriction แยก policy shock จาก info shock (R2)
    5. Balance sheet channel — sector leverage สูงไวต่อต้นทุนรีไฟแนนซ์ (channel C7)
    6. NBER w32884 (2024) — duration channel (term structure ของ yield) เป็นกลไกหลัก มากกว่า
       equity premium — สนับสนุนว่า C1 (duration) ควรมีน้ำหนักสำคัญในโมเดลนี้

รัน unit test: python3 -m model_c_rulebase.engine.test_sector_rules
"""

from dataclasses import dataclass, field
from typing import Optional

SECTORS = ["XLK", "XLC", "XLY", "XLP", "XLV", "XLF", "XLI", "XLB", "XLE", "XLU", "XLRE"]
CHANNELS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]

CHANNEL_NAMES = {
    "C1": "Duration / discount rate",
    "C2": "Cyclical growth beta",
    "C3": "Net interest margin (curve slope)",
    "C4": "Credit risk",
    "C5": "Dollar",
    "C6": "Inflation pass-through",
    "C7": "Leverage / refinancing",
}

# --------------------------------------------------------------------------
# Sector loading matrix — ค่าเริ่มต้นจากทฤษฎี (ห้ามถือเป็นค่าจริง — ดู docstring ด้านบน)
# XLF C3="n/a" -> ให้เป็น 0.0 ที่ตัดใช้จริง แต่ flag ไว้ว่า "not applicable" ในคำอธิบาย ไม่ใช่
# 0 เฉยๆ แบบ silent (leverage channel ไม่มีความหมายชัดเจนสำหรับธนาคารในกรอบนี้ เพราะขนาด
# balance sheet คือตัวธุรกิจธนาคารเอง ไม่ใช่ "หนี้" ในความหมายเดียวกับบริษัททั่วไป)
# --------------------------------------------------------------------------

LOADING_MATRIX = {
    "XLK":  {"C1": -1.0, "C2": 0.5, "C3": 0.0, "C4": 0.0, "C5": -0.5, "C6": -0.4, "C7": -0.2},
    "XLC":  {"C1": -0.6, "C2": 0.4, "C3": 0.0, "C4": 0.0, "C5": -0.2, "C6": -0.2, "C7": -0.5},
    "XLY":  {"C1": -0.5, "C2": 0.9, "C3": 0.0, "C4": -0.7, "C5": -0.2, "C6": -0.4, "C7": -0.4},
    "XLP":  {"C1": -0.4, "C2": 0.1, "C3": 0.0, "C4": -0.1, "C5": -0.2, "C6": -0.2, "C7": -0.2},
    "XLV":  {"C1": -0.4, "C2": 0.1, "C3": 0.0, "C4": 0.0, "C5": -0.2, "C6": -0.1, "C7": -0.2},
    "XLF":  {"C1": -0.2, "C2": 0.5, "C3": 0.9, "C4": -0.8, "C5": 0.0, "C6": 0.0, "C7": 0.0},
    "XLI":  {"C1": -0.3, "C2": 0.9, "C3": 0.0, "C4": -0.4, "C5": -0.4, "C6": 0.0, "C7": -0.4},
    "XLB":  {"C1": -0.3, "C2": 0.8, "C3": 0.0, "C4": -0.3, "C5": -0.7, "C6": 0.6, "C7": -0.4},
    "XLE":  {"C1": -0.2, "C2": 0.5, "C3": 0.0, "C4": -0.2, "C5": -0.6, "C6": 0.9, "C7": -0.3},
    "XLU":  {"C1": -0.9, "C2": 0.1, "C3": 0.0, "C4": 0.0, "C5": 0.0, "C6": -0.3, "C7": -0.8},
    "XLRE": {"C1": -1.0, "C2": 0.4, "C3": 0.0, "C4": -0.5, "C5": 0.0, "C6": 0.2, "C7": -0.9},
}

LOADING_NA = {"XLF": {"C7"}}  # sector -> channel ที่ระบุ "n/a" ในสเปก (ไม่ใช่ 0 ทางทฤษฎี)

# --------------------------------------------------------------------------
# Channel-activation constants — **ตีความเองจากคำอธิบายเชิงคุณภาพในสเปก ไม่ใช่ค่าทฤษฎีตรงๆ**
# (ต้อง calibrate ใน R6 เหมือน loading matrix — ดูหมายเหตุใน module docstring)
# --------------------------------------------------------------------------

C1_DAMPENER = {  # "policy_tightening → C1↓ (เต็ม) | info_positive → C1↓ อ่อน (มีกำไรชดเชย)"
    "policy_tightening": 1.0,
    "info_positive": 0.5,
    "policy_easing": 1.0,
    "info_negative": 1.0,
    "no_rate_surprise": 1.0,
}

C2_AMPLIFIER = {  # "info_positive/info_negative → C2 แรง" (Fed information effect เด่นชัดสุด
                  # ตรงนี้ตามทฤษฎี Nakamura-Steinsson) ส่วน policy_* ไม่ได้ระบุว่า "แรง" -> 1.0
    "info_positive": 1.5,
    "info_negative": 1.5,
}
C2_AMPLIFIER_DEFAULT = 1.0

C7_BALANCE_SHEET_WEIGHT = 0.3  # น้ำหนักเสริมของ balance_sheet_signal (QT/QE) ต่อ C7 นอกเหนือจาก
                                # rate_surprise หลัก — QT ระบายสภาพคล่องเพิ่มเติมนอกจากผลของ
                                # อัตราดอกเบี้ยเอง (balance sheet channel, item 5 ในทฤษฎีอ้างอิง)

VIX_AMPLIFIER_RANGE = (1.3, 1.5)  # ตามสเปก "คูณ amplitude ทั้งหมด 1.3-1.5 เท่า" — ใช้ค่ากลาง
VIX_AMPLIFIER = sum(VIX_AMPLIFIER_RANGE) / 2  # = 1.4

LOW_CONFIDENCE_DAMPENER = 0.5  # ตามสเปก "low_confidence dampener: คูณ 0.5"

# XLF pivot — เกณฑ์ตามสเปก: financial_stability_concern>=1 หรือ curve_slope_delta<0 (แบน/กลับหัว)
XLF_PIVOT_C3_LOADING = 0.2   # ลดจาก 0.9 ปกติ (NIM สำคัญน้อยลงเมื่อตลาดกลัวเครดิต)
XLF_PIVOT_C4_LOADING = -1.5  # เพิ่มขนาดจาก -0.8 ปกติ (เครดิตริสก์กลายเป็นตัวหลัก)


@dataclass
class MarketContext:
    rate_surprise: float
    equity_move: float
    curve_slope_delta: float
    vix_delta: float
    dxy_delta: Optional[float]  # None ถ้าไม่มีข้อมูล (เช่น ข่าวก่อน 2006 ที่ DTWEXBGS ไม่มีข้อมูล)
    shock_type: str


@dataclass
class StructuredVars:
    stance_delta: int = 0
    growth_delta: int = 0
    inflation_delta: int = 0
    labor_delta: int = 0
    forward_guidance_delta: int = 0
    balance_sheet_signal: int = 0
    uncertainty_language: int = 0
    financial_stability_concern: int = 0
    low_confidence: bool = False


@dataclass
class ChannelResult:
    activation: dict = field(default_factory=dict)
    explanation: dict = field(default_factory=dict)


def compute_channel_activations(market: MarketContext, llm: StructuredVars) -> ChannelResult:
    """คำนวณ "activation" ของแต่ละ channel (ค่าที่ยังไม่คูณ loading matrix) พร้อมคำอธิบายที่มา
    เป็นข้อความ ทุก field อ้างอิงตัวแปรจริงที่ใช้คำนวณเสมอ (ตรวจสอบย้อนได้)

    Sign convention: activation ค่าบวก = channel นั้น "แย่" สำหรับ sector ที่มี loading ติดลบ
    ในช่องนั้น (เช่น C1 บวก = discount rate สูงขึ้น = duration-sensitive sector โดน)"""
    act, exp = {}, {}

    # C1: duration/discount rate — ตาม rate_surprise โดยตรง, ลดทอนถ้าเป็น info_positive
    # (ดอกเบี้ยขึ้นแต่ตลาดมองว่ามีกำไรชดเชย ผลกระทบ duration เบาลง)
    dampener = C1_DAMPENER.get(market.shock_type, 1.0)
    act["C1"] = market.rate_surprise * dampener
    exp["C1"] = (f"rate_surprise({market.rate_surprise:+.3f}) x dampener({dampener}) "
                 f"[{market.shock_type}]")

    # C2: cyclical growth beta — ตาม growth_delta (LLM) โดยตรง, ขยายสำหรับ info_positive/negative
    # (Fed information effect: ตลาดในสองกลุ่มนี้ตอบสนองผ่านการอ่าน "แนวโน้มเศรษฐกิจ" เป็นหลัก)
    amp = C2_AMPLIFIER.get(market.shock_type, C2_AMPLIFIER_DEFAULT)
    act["C2"] = llm.growth_delta * amp
    exp["C2"] = f"growth_delta({llm.growth_delta:+d}) x amplifier({amp}) [{market.shock_type}]"

    # C3: NIM — ตาม curve_slope_delta โดยตรง เป็นกลไกโครงสร้าง (ความชันของ curve กำหนดส่วนต่าง
    # ดอกเบี้ยกู้ยืม-ให้กู้ของธนาคาร) ใช้เหมือนกันทุก shock_type ไม่ผูกกับ quadrant
    act["C3"] = market.curve_slope_delta
    exp["C3"] = f"curve_slope_delta({market.curve_slope_delta:+.3f}) [ใช้เหมือนกันทุก shock_type]"

    # C4: credit risk — กลไกต่างกันตาม quadrant (ตามสเปก):
    #   policy_tightening: activate เฉพาะเมื่อมีภาษาความไม่แน่นอน/ความเสี่ยงเสถียรภาพการเงินสูง
    #                       (ตึงตัวเฉยๆ ไม่พอ ต้องมี "สัญญาณเตือน" จากเนื้อหาจริงด้วย)
    #   info_positive/negative: ผูกตรงกับ growth_delta ตรงข้าม (มองเศรษฐกิจดีขึ้น = credit risk ลง)
    #   policy_easing: ไม่ได้ระบุกลไกไว้ในสเปก -> ไม่ activate (0) ไม่เดาเพิ่ม
    if market.shock_type == "policy_tightening":
        stress = max(llm.uncertainty_language, llm.financial_stability_concern)
        act["C4"] = float(stress)
        exp["C4"] = (f"max(uncertainty_language={llm.uncertainty_language}, "
                      f"financial_stability_concern={llm.financial_stability_concern}) "
                      f"[activate เฉพาะ policy_tightening ตามสเปก]")
    elif market.shock_type in ("info_positive", "info_negative"):
        act["C4"] = -float(llm.growth_delta)
        exp["C4"] = f"-growth_delta({llm.growth_delta:+d}) [info shock: credit risk ผูกกับมุมมองเศรษฐกิจ]"
    else:
        act["C4"] = 0.0
        exp["C4"] = f"0 (ไม่ได้ระบุกลไก C4 สำหรับ {market.shock_type} ในสเปก — ไม่เดาเพิ่ม)"

    # C5: dollar — mechanical, dxy_delta ตรงๆ, ถ้าไม่มีข้อมูล (ก่อน 2006) -> 0 พร้อม flag ชัดเจน
    if market.dxy_delta is None:
        act["C5"] = 0.0
        exp["C5"] = "0 (dxy_delta ไม่มีข้อมูล — DTWEXBGS เริ่ม 2006-01-02, ข่าวนี้เก่ากว่านั้น)"
    else:
        act["C5"] = market.dxy_delta
        exp["C5"] = f"dxy_delta({market.dxy_delta:+.3f})"

    # C6: inflation pass-through — ตาม inflation_delta (LLM) โดยตรง
    act["C6"] = float(llm.inflation_delta)
    exp["C6"] = f"inflation_delta({llm.inflation_delta:+d})"

    # C7: leverage/refinancing — rate_surprise (ต้นทุนรีไฟแนนซ์ตามระดับดอกเบี้ย) +
    # balance_sheet_signal ถ่วงน้ำหนักเสริม (QT ระบายสภาพคล่องเพิ่มนอกเหนือระดับดอกเบี้ยเอง)
    act["C7"] = market.rate_surprise + C7_BALANCE_SHEET_WEIGHT * llm.balance_sheet_signal
    exp["C7"] = (f"rate_surprise({market.rate_surprise:+.3f}) + "
                 f"{C7_BALANCE_SHEET_WEIGHT}*balance_sheet_signal({llm.balance_sheet_signal:+d})")

    return ChannelResult(activation=act, explanation=exp)


def _sector_loading(sector: str, market: MarketContext, llm: StructuredVars) -> tuple:
    """คืน (loading_dict, pivot_note_or_None) ของ sector หนึ่งตัว — ใช้ loading ปกติ ยกเว้น
    XLF ที่เข้าเงื่อนไข pivot (financial_stability_concern>=1 หรือ curve_slope_delta<0)"""
    base = dict(LOADING_MATRIX[sector])
    if sector == "XLF":
        pivot = llm.financial_stability_concern >= 1 or market.curve_slope_delta < 0
        if pivot:
            note = (f"XLF pivot ACTIVE (financial_stability_concern={llm.financial_stability_concern}"
                     f" >= 1 หรือ curve_slope_delta={market.curve_slope_delta:+.3f} < 0) — "
                     f"C3 loading {base['C3']} -> {XLF_PIVOT_C3_LOADING}, "
                     f"C4 loading {base['C4']} -> {XLF_PIVOT_C4_LOADING} "
                     f"(เครดิตริสก์กลายเป็นตัวหลักแทน NIM — เคสอ้างอิง: วิกฤตธนาคารภูมิภาค มี.ค. 2023)")
            base["C3"] = XLF_PIVOT_C3_LOADING
            base["C4"] = XLF_PIVOT_C4_LOADING
            return base, note
    return base, None


def score_event(market: MarketContext, llm: StructuredVars, vix_p90: float) -> dict:
    """คำนวณ sector_impact_score ของทั้ง 11 sector จาก event เดียว คืน dict:
        {
          "channels": {...},               # activation ดิบ + คำอธิบายจาก compute_channel_activations
          "vix_amplifier_active": bool,
          "low_confidence_dampener_active": bool,
          "sectors": {
              "XLK": {"score": float, "contributions": {C1:..,...}, "notes": [...]},
              ...
          }
        }

    vix_p90: เกณฑ์ 90th percentile ของ vix_delta ที่คำนวณจากข้อมูลจริง (ห้ามเดา/hardcode ลอยๆ
    ในฟังก์ชันนี้ — ผู้เรียกต้องคำนวณจาก fomc_market_context.csv จริงแล้วส่งเข้ามา)
    """
    channel_result = compute_channel_activations(market, llm)

    vix_amplifier_active = market.vix_delta > vix_p90
    global_multiplier = VIX_AMPLIFIER if vix_amplifier_active else 1.0
    if llm.low_confidence:
        global_multiplier *= LOW_CONFIDENCE_DAMPENER

    sectors_out = {}
    for sector in SECTORS:
        loading, pivot_note = _sector_loading(sector, market, llm)
        contributions = {}
        for c in CHANNELS:
            raw_contribution = channel_result.activation[c] * loading[c]
            contributions[c] = raw_contribution * global_multiplier
        score = sum(contributions.values())

        notes = []
        if pivot_note:
            notes.append(pivot_note)
        if vix_amplifier_active:
            notes.append(f"VIX amplifier ACTIVE (vix_delta={market.vix_delta:+.2f} > "
                          f"p90={vix_p90:.2f}) — คูณคะแนนรวม x{VIX_AMPLIFIER}")
        if llm.low_confidence:
            notes.append(f"low_confidence dampener ACTIVE — คูณคะแนนรวม x{LOW_CONFIDENCE_DAMPENER}")
        na_channels = LOADING_NA.get(sector, set())
        if na_channels:
            notes.append(f"channel {sorted(na_channels)} ระบุ 'n/a' ในสเปกต้นฉบับ (ใช้ loading=0 "
                          f"แทน แต่ไม่ใช่ 0 เชิงทฤษฎี — ดู module docstring)")

        sectors_out[sector] = {
            "score": score,
            "loading_used": loading,
            "contributions": contributions,
            "notes": notes,
        }

    return {
        "shock_type": market.shock_type,
        "channels": {"activation": channel_result.activation, "explanation": channel_result.explanation},
        "vix_amplifier_active": vix_amplifier_active,
        "low_confidence_dampener_active": llm.low_confidence,
        "global_multiplier": global_multiplier,
        "sectors": sectors_out,
    }


def explain(result: dict, sector: str) -> str:
    """คืนคำอธิบายแบบอ่านง่ายของคะแนน sector หนึ่งตัวจากผล score_event() — ใช้สำหรับรายงาน/debug
    (explainability requirement: ทุกคะแนนต้องอธิบายที่มาได้)"""
    s = result["sectors"][sector]
    lines = [f"{sector}: score = {s['score']:+.4f} (shock_type={result['shock_type']})"]
    for c in CHANNELS:
        act_exp = result["channels"]["explanation"][c]
        contrib = s["contributions"][c]
        loading = s["loading_used"][c]
        lines.append(f"  {c} ({CHANNEL_NAMES[c]}): activation=[{act_exp}], "
                     f"loading={loading:+.2f}, contribution={contrib:+.4f}")
    for n in s["notes"]:
        lines.append(f"  NOTE: {n}")
    return "\n".join(lines)
