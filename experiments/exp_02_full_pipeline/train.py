"""
exp_02_full_pipeline/train.py — Full pipeline: baseline + FinBERT sentiment features

Features: sector (one-hot) + VIX + US10Y + sent_XLK...sent_XLC (11 คอลัมน์ จาก sentiment.parquet)
Target  : label (-2,-1,0,1,2) จาก data/processed/labels.parquet
Model   : XGBoost multiclass, pooled — เหมือน exp_01 ทุกประการ (ใช้ common.py ร่วมกัน)
          ต่างกันแค่เพิ่ม sentiment feature เข้าไป
Split   : ตามคอลัมน์ split ใน labels.parquet (เรียงเวลา, test = 2 ปีสุดท้าย, ห้ามสุ่ม)

Output  : experiments/exp_02_full_pipeline/metrics.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    log, load_labels, fetch_macro_features, attach_macro, attach_sentiment,
    build_features, train_xgb, compute_metrics, feature_importance_top_n, save_json,
)

EXP_DIR = Path(__file__).resolve().parent
METRICS_PATH = EXP_DIR / "metrics.json"


def main():
    log.info("=== exp_02_full_pipeline ===")

    labels = load_labels()
    log.info(f"Loaded labels: {len(labels)} rows")

    macro = fetch_macro_features()
    df = attach_macro(labels, macro)

    df, sent_cols = attach_sentiment(df)
    n_missing_sent = df[sent_cols].isna().any(axis=1).sum()
    if n_missing_sent:
        log.warning(f"{n_missing_sent} แถวไม่มี sentiment ให้ merge (url ไม่พบใน sentiment.parquet) — ตัดทิ้ง ไม่เดา")

    n_before = len(df)
    df = df.dropna(subset=["VIX", "US10Y"] + sent_cols)
    n_dropped = n_before - len(df)
    if n_dropped:
        log.warning(f"ตัด {n_dropped} แถวที่ข้อมูลไม่ครบ (VIX/US10Y/sentiment) รวม (ไม่เดา)")

    X, y, feature_names = build_features(df, extra_cols=sent_cols)
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
