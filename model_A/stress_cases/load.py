"""อ่านและตรวจรูปแบบไฟล์เคสหุ้นเจ๊ง — ⛔ ห้ามเรียกจาก lib/, rounds/ หรือ export/build_scores.py (ห้ามปนกับข้อมูลคัดเลือกกฎ)"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def load(path=HERE / "cases_template.csv") -> pd.DataFrame:
    df = pd.read_csv(path, comment="#", dtype={"ticker": str, "case_id": str})
    need = ["case_id", "ticker", "date", "price", "note"]
    missing = [c for c in need if c not in df.columns]
    assert not missing, f"ขาดคอลัมน์ {missing}"
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["price"] = pd.to_numeric(df["price"], errors="raise")
    assert (df["price"] >= 0).all(), "ราคาต้อง ≥ 0"
    return df.sort_values(["case_id", "date"]).reset_index(drop=True)


if __name__ == "__main__":
    d = load(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "cases_template.csv")
    print(d.groupby("case_id").agg(ticker=("ticker", "first"), start=("date", "min"), end=("date", "max"),
                                   first_price=("price", "first"), last_price=("price", "last"), points=("price", "size")))
