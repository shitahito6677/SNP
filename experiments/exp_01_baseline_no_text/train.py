"""
exp_01_baseline_no_text/train.py — Baseline: ไม่ใช้ข้อมูลข่าว/sentiment เลย

Features: sector (one-hot) + VIX + US10Y
Target  : label (-2,-1,0,1,2) จาก data/processed/labels.parquet
Model   : XGBoost multiclass, pooled (โมเดลเดียว sector เป็น feature ไม่แยกโมเดลต่อ sector)
Split   : ตามคอลัมน์ split ใน labels.parquet (เรียงเวลา, test = 2 ปีสุดท้าย, ห้ามสุ่ม)

Output  : experiments/exp_01_baseline_no_text/metrics.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    log, load_labels, fetch_macro_features, attach_macro,
    build_features, train_xgb, compute_metrics, feature_importance_top_n, save_json,
)

EXP_DIR = Path(__file__).resolve().parent
METRICS_PATH = EXP_DIR / "metrics.json"


def main():
    log.info("=== exp_01_baseline_no_text ===")

    labels = load_labels()
    log.info(f"Loaded labels: {len(labels)} rows")

    macro = fetch_macro_features()
    df = attach_macro(labels, macro)

    n_before = len(df)
    df = df.dropna(subset=["VIX", "US10Y"])
    n_dropped = n_before - len(df)
    if n_dropped:
        log.warning(f"ตัด {n_dropped} แถวที่ไม่มีค่า VIX/US10Y (ไม่เดา)")

    X, y, feature_names = build_features(df)
    log.info(f"Features ({len(feature_names)}): {feature_names}")

    train_mask = (df["split"] == "train").values
    test_mask = (df["split"] == "test").values
    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    log.info(f"train={len(X_train)}, test={len(X_test)}")

    model, y_pred = train_xgb(X_train, y_train, X_test, y_test)
    metrics = compute_metrics(y_test, y_pred)
    metrics["n_train"] = int(len(X_train))
    metrics["feature_names"] = feature_names
    metrics["feature_importance_top10"] = feature_importance_top_n(model, feature_names, n=10)

    save_json(METRICS_PATH, metrics)

    log.info(f"accuracy={metrics['accuracy']:.4f}, macro_f1={metrics['macro_f1']:.4f}")
    log.info(f"per_class_f1={metrics['per_class_f1']}")
    log.info(f"Saved -> {METRICS_PATH}")


if __name__ == "__main__":
    main()
