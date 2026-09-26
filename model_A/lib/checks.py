"""
Assertion กันบั๊กเงียบ (ผู้ใช้ขอหลัง v0) — บั๊กที่เคยเจอใน v0 ทั้ง 2 ตัวเป็นแบบ "ไม่ error แต่ข้อมูลหาย":
  - SEC RSS เปลี่ยน namespace → parse ได้ 0 แถว
  - tag priority → งบปี 2017 หายในรอบ มิ.ย. 2018 (ลดจาก ~90% เหลือ 42%)
ทุกฟังก์ชัน raise AssertionError พร้อมข้อความที่บอกว่าผิดตรงไหน
"""

import pandas as pd


def nonempty(df: pd.DataFrame, name: str, min_rows: int = 1) -> None:
    assert df is not None and len(df) >= min_rows, f"[{name}] มี {0 if df is None else len(df)} แถว (ต้อง >= {min_rows})"


def members_per_R(panel: pd.DataFrame, lo: int = 480, hi: int = 520) -> None:
    n = panel.groupby("R").size()
    bad = n[(n < lo) | (n > hi)]
    assert bad.empty, f"จำนวนสมาชิกต่อรอบผิดปกติ (ต้องอยู่ใน {lo}-{hi}): {bad.to_dict()}"


def no_sudden_drop(panel: pd.DataFrame, col: str, since="2012-01-01", frac: float = 0.8, mask=None) -> None:
    """จำนวนหุ้นที่ col=True ในแต่ละรอบ ต้องไม่ต่ำกว่า frac × ค่าเฉลี่ยของรอบก่อนหน้าและรอบถัดไป
    (จับ "หลุมรายปี" แบบบั๊ก 2018 ที่ตกจาก ~390 เหลือ ~200 — ไม่เทียบกับ median ทั้งช่วง เพราะความครอบคลุม
    เพิ่มขึ้นตามเวลาจริง ๆ จาก survivorship ทำให้ช่วงต้นต่ำกว่า median โดยไม่ใช่บั๊ก)"""
    p = panel if mask is None else panel[mask]
    n = p[p["R"] >= pd.Timestamp(since)].groupby("R")[col].sum().sort_index()
    ref = pd.concat([n.shift(1), n.shift(-1)], axis=1).mean(axis=1)
    bad = n[n < frac * ref]
    assert bad.empty, f"[{col}] จำนวนต่อรอบตกเป็นหลุม (< {frac} × เฉลี่ยรอบข้างเคียง): {bad.to_dict()}"


def unique_keys(df: pd.DataFrame, keys: list, name: str) -> None:
    d = df.duplicated(keys).sum()
    assert d == 0, f"[{name}] key ซ้ำ {d} แถว บน {keys}"


def segments_valid(segs: pd.DataFrame) -> None:
    bad = segs[segs["valid_to"].notna() & (segs["valid_to"] < segs["valid_from"])]
    assert bad.empty, f"CIK segment ช่วงเวลากลับหัว {len(bad)} แถว: {bad[['ticker', 'valid_from', 'valid_to']].head().to_dict('records')}"
