"""
s4_sentiment.py — ขั้นที่ 4: ให้ FinBERT ให้คะแนน sentiment ของ sector view แต่ละอัน

Input : data/processed/sector_views.parquet   (จาก s3_sector_views.py)
Output: data/processed/sentiment.parquet      (date, source, url, sent_XLK...sent_XLC)

Model : ProsusAI/finbert (HuggingFace) — 3-class sentiment (positive/negative/neutral)
คะแนน : score = P(positive) - P(negative)  จาก softmax logits, อยู่ในช่วง [-1, 1]
        (ไม่รวม P(neutral) ในสูตรตามที่กำหนด — neutral สูง จะดึงคะแนนเข้าใกล้ 0 โดยอัตโนมัติ
         อยู่แล้วเพราะ P(positive)+P(negative)+P(neutral)=1)
"""

import logging
import time
from pathlib import Path

import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN_PATH = PROJECT_ROOT / "data" / "processed" / "sector_views.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "sentiment.parquet"

MODEL_NAME = "ProsusAI/finbert"
SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
BATCH_SIZE = 32

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("s4_sentiment")


def load_model():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    log.info(f"Loading {MODEL_NAME} ... (device={device})")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    model.to(device)
    model.eval()

    # FinBERT label order ตาม config ของ ProsusAI/finbert คือ [positive, negative, neutral]
    id2label = model.config.id2label
    log.info(f"model id2label: {id2label}")
    labels_lower = {i: lbl.lower() for i, lbl in id2label.items()}
    idx_pos = [i for i, l in labels_lower.items() if l == "positive"][0]
    idx_neg = [i for i, l in labels_lower.items() if l == "negative"][0]

    return tokenizer, model, device, idx_pos, idx_neg


@torch.no_grad()
def score_texts(texts, tokenizer, model, device, idx_pos, idx_neg, batch_size=BATCH_SIZE):
    """คืน list ของ score = P(positive) - P(negative) เรียงตามลำดับ texts"""
    scores = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=256)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        batch_scores = (probs[:, idx_pos] - probs[:, idx_neg]).cpu().tolist()
        scores.extend(batch_scores)
    return scores


def main():
    if not IN_PATH.exists():
        raise FileNotFoundError(f"ไม่พบ {IN_PATH} — รัน s3_sector_views.py ก่อน")

    t_start = time.time()

    df = pd.read_parquet(IN_PATH)
    log.info(f"Loaded {len(df)} rows from {IN_PATH}")

    tokenizer, model, device, idx_pos, idx_neg = load_model()

    out = df[["date", "source", "url"]].copy()

    for tk in SECTORS:
        col = f"view_{tk}"
        log.info(f"Scoring sector {tk} ({len(df)} texts)...")
        t0 = time.time()
        scores = score_texts(df[col].tolist(), tokenizer, model, device, idx_pos, idx_neg)
        out[f"sent_{tk}"] = scores
        log.info(f"  done in {time.time()-t0:.1f}s")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)

    elapsed = time.time() - t_start

    # --------------------- รายงานผล ---------------------
    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"เวลาที่ใช้รันทั้งหมด: {elapsed:.1f} วินาที ({elapsed/60:.1f} นาที), device={device}")
    log.info(f"Saved to: {OUT_PATH}  ({len(out)} rows)")

    log.info("\nตัวอย่าง 5 แถวแรก:")
    cols_show = ["date", "source"] + [f"sent_{tk}" for tk in SECTORS]
    with pd.option_context("display.max_columns", None, "display.width", 200):
        log.info("\n" + out[cols_show].head(5).to_string())

    log.info("\nDistribution คะแนนแต่ละ sector (min, mean, median, max):")
    stats = out[[f"sent_{tk}" for tk in SECTORS]].agg(["min", "mean", "median", "max"]).T
    log.info("\n" + stats.to_string())

    log.info("\nเช็คพิเศษ: XLP vs XLV (คาดว่า cluster ใกล้ 0 เพราะ Qwen เขียน neutral บ่อย):")
    for tk in ["XLP", "XLV"]:
        s = out[f"sent_{tk}"]
        log.info(
            f"  {tk}: min={s.min():.3f}, mean={s.mean():.3f}, median={s.median():.3f}, "
            f"max={s.max():.3f}, std={s.std():.3f}, "
            f"|score|<0.1 = {(s.abs() < 0.1).mean()*100:.1f}%"
        )

    return out


if __name__ == "__main__":
    main()
