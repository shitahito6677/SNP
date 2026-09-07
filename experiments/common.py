"""
common.py — โค้ดที่ใช้ร่วมกันระหว่าง exp_01 และ exp_02 เพื่อการันตีว่า
"ทุกอย่างอื่นเหมือนกันเป๊ะ" ยกเว้นการมี/ไม่มี sentiment feature (สั่งจากผู้ใช้)
ไม่ต้อง copy-paste logic ระหว่าง 2 experiment ให้เสี่ยงหลุด sync กัน
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import yfinance as yf
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABELS_PATH = PROJECT_ROOT / "data" / "processed" / "labels.parquet"
SENTIMENT_PATH = PROJECT_ROOT / "data" / "processed" / "sentiment.parquet"
MACRO_CACHE_PATH = PROJECT_ROOT / "data" / "raw" / "macro_features_raw.parquet"

SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
CLASS_LABELS = [-2, -1, 0, 1, 2]  # ลำดับ class คงที่ ใช้ตัดสิน confusion matrix/per-class f1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("experiments.common")


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

def load_labels():
    df = pd.read_parquet(LABELS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_macro_features():
    """ดาวน์โหลด VIX (^VIX) และ US10Y (^TNX) close รายวัน แคชไว้ที่ data/raw/
    เพื่อไม่ต้องดาวน์โหลดซ้ำทุกครั้งที่รัน exp_01/exp_02"""
    if MACRO_CACHE_PATH.exists():
        log.info(f"ใช้ macro feature cache เดิม: {MACRO_CACHE_PATH}")
        return pd.read_parquet(MACRO_CACHE_PATH)

    log.info("Downloading ^VIX, ^TNX from yfinance ...")
    raw = yf.download(["^VIX", "^TNX"], start="1996-01-01", auto_adjust=False, progress=False)
    macro = pd.DataFrame({
        "VIX": raw["Close"]["^VIX"],
        "US10Y": raw["Close"]["^TNX"],
    }).dropna().sort_index()

    MACRO_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    macro.to_parquet(MACRO_CACHE_PATH)
    log.info(f"Saved macro feature cache -> {MACRO_CACHE_PATH} ({len(macro)} trading days)")
    return macro


def attach_macro(df, macro):
    """merge_asof แบบ backward: เอาค่า VIX/US10Y ของ trading day ล่าสุดที่ <= วันข่าว
    (กันกรณีวันข่าวไม่ตรงกับ trading day ของ VIX/TNX เป๊ะๆ)"""
    macro_sorted = macro.copy()
    macro_sorted.index.name = "date"
    macro_sorted = macro_sorted.reset_index().sort_values("date")
    df_sorted = df.sort_values("date")
    merged = pd.merge_asof(df_sorted, macro_sorted, on="date", direction="backward")
    return merged


def attach_sentiment(df):
    """แนบ sent_XLK...sent_XLC ทั้ง 11 คอลัมน์จาก sentiment.parquet เข้ากับทุกแถวของข่าวนั้น
    (broadcast ตาม url — 1 ข่าวมี sentiment vector เดียว ใช้ร่วมกันได้ทุก sector-row ของข่าวนั้น)"""
    sentiment = pd.read_parquet(SENTIMENT_PATH)
    sent_cols = [f"sent_{tk}" for tk in SECTORS]
    merged = df.merge(sentiment[["url"] + sent_cols], on="url", how="left")
    return merged, sent_cols


# --------------------------------------------------------------------------
# Feature building
# --------------------------------------------------------------------------

def build_features(df, extra_cols=None):
    """สร้าง X (sector one-hot + VIX + US10Y [+ extra_cols]), y (label แปลงเป็น class index 0-4)
    คืน X, y, feature_names, class_index_to_label"""
    sector_dummies = pd.get_dummies(
        pd.Categorical(df["sector"], categories=SECTORS), prefix="sector"
    )
    base_cols = ["VIX", "US10Y"]
    extra_cols = extra_cols or []

    X = pd.concat([sector_dummies.reset_index(drop=True),
                   df[base_cols + extra_cols].reset_index(drop=True)], axis=1)
    feature_names = list(X.columns)

    label_to_idx = {lbl: i for i, lbl in enumerate(CLASS_LABELS)}
    y = df["label"].map(label_to_idx).values

    return X.values.astype(float), y, feature_names


# --------------------------------------------------------------------------
# Train + evaluate
# --------------------------------------------------------------------------

def train_xgb(X_train, y_train, X_test, y_test, seed=42):
    model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=len(CLASS_LABELS),
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=seed,
        eval_metric="mlogloss",
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    return model, y_pred


def compute_metrics(y_test, y_pred):
    acc = accuracy_score(y_test, y_pred)
    macro_f1 = f1_score(y_test, y_pred, average="macro", labels=list(range(len(CLASS_LABELS))))
    per_class_f1 = f1_score(y_test, y_pred, average=None, labels=list(range(len(CLASS_LABELS))))
    cm = confusion_matrix(y_test, y_pred, labels=list(range(len(CLASS_LABELS))))

    return {
        "accuracy": float(acc),
        "macro_f1": float(macro_f1),
        "per_class_f1": {str(lbl): float(f1) for lbl, f1 in zip(CLASS_LABELS, per_class_f1)},
        "confusion_matrix": {
            "labels": CLASS_LABELS,
            "matrix": cm.tolist(),
            "note": "row = actual class, column = predicted class, ลำดับตาม labels ข้างบน",
        },
        "n_test": int(len(y_test)),
    }


def feature_importance_top_n(model, feature_names, n=10):
    booster = model.get_booster()
    gain_scores = booster.get_score(importance_type="gain")  # key เป็น 'f0','f1',...
    named = {feature_names[int(k[1:])]: v for k, v in gain_scores.items()}
    top = sorted(named.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"feature": k, "gain": float(v)} for k, v in top]


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
