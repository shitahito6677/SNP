"""
e3_clustering.py — exp_04 Phase E3: clustering price-path feature ต่อ sector (คณิตศาสตร์ล้วนๆ
K-means + silhouette + bootstrap stability — ไม่มี LLM เกี่ยวข้องเลยตามที่กำหนด)

**ทำไมแยกทำทีละ sector:** base rate ของแต่ละ sector ต่างกันมาก (เช่น XLU defensive เทียบ XLK
cyclical) รวมทุก sector เข้าด้วยกันจะทำให้ cluster ที่เจอเป็นแค่ "sector identity" ไม่ใช่ "รูปแบบ
การเคลื่อนไหวราคา" ที่ตั้งใจหา

**Feature ที่ใช้ (ทั้งหมดจาก E2 ไม่คัดเลือกบางส่วน — กัน fishing โดยเลือกเฉพาะ feature ที่ทำให้
cluster ออกมาสวย):** `cum_return_pre`, `cum_return_post_short`, `cum_return_post_full`,
`peak_offset`, `peak_value`, `reversion_ratio` — standardize (z-score) ก่อน fit เสมอ

**วิธีเลือก k (k=3..5, K-means, random_state คงที่กันผลเปลี่ยนทุกครั้งที่รัน):**
    1. Fit K-means บนข้อมูลเต็มของ sector นั้น -> คำนวณ silhouette score
    2. **Bootstrap stability:** resample ข้อมูล (with replacement, ขนาดเท่าเดิม) 100 รอบ, fit
       K-means เดียวกัน (k เดียวกัน) บน resample แต่ละรอบ แล้วใช้ centroid ที่ได้ predict label
       ของข้อมูล**เต็มชุดเดิม** (ไม่ใช่แค่ตัว resample) เทียบกับ label จาก fit เต็มชุดเดิม (ข้อ 1)
       ด้วย Adjusted Rand Index (ARI) — ค่าเฉลี่ย ARI จาก 100 รอบ = stability score ของ k นั้น
    3. เลือก k จาก **k ที่ stability (ARI เฉลี่ย) >= 0.5 เท่านั้น** แล้วในกลุ่มนั้นเลือก k ที่
       silhouette สูงสุด — ถ้าไม่มี k ไหนผ่าน ARI>=0.5 เลย ให้สรุปตรงๆ ว่า sector นั้น**ไม่มี
       cluster ที่เสถียร** (ไม่ฝืนเลือก k ที่ ARI ต่ำสุดมาใช้)

Input : model_c_event_clustering/data/event_features.csv (E2)
Output: model_c_event_clustering/data/e3_cluster_assignments.csv (เฉพาะ sector ที่มี cluster
        เสถียร — 1 แถว ต่อ ข่าว x sector x cluster_label)
        model_c_event_clustering/data/e3_stability_report.csv (ทุก sector x ทุก k ที่ลอง)

รัน: python3 -m model_c_event_clustering.scripts.e3_clustering
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "model_c_event_clustering" / "data"
FEATURES_CSV = DATA_DIR / "event_features.csv"
OUT_ASSIGNMENTS = DATA_DIR / "e3_cluster_assignments.csv"
OUT_STABILITY = DATA_DIR / "e3_stability_report.csv"

FEATURE_COLS = ["cum_return_pre", "cum_return_post_short", "cum_return_post_full",
                 "peak_offset", "peak_value", "reversion_ratio"]

K_RANGE = [3, 4, 5]
N_BOOT = 100
ARI_STABILITY_THRESHOLD = 0.5
RANDOM_SEED = 42

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("e3_clustering")


def bootstrap_ari(X: np.ndarray, k: int, rng: np.random.Generator, n_boot: int = N_BOOT):
    n = X.shape[0]
    ref_km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_SEED).fit(X)
    ref_labels = ref_km.labels_

    aris = []
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_SEED + b + 1).fit(X[idx])
        pred_on_full = boot_km.predict(X)
        aris.append(adjusted_rand_score(ref_labels, pred_on_full))

    return ref_labels, float(np.mean(aris)), float(np.std(aris))


def main():
    feats = pd.read_csv(FEATURES_CSV)
    log.info(f"โหลด feature {len(feats)} แถว ({feats['sector'].nunique()} sector)")

    stability_rows = []
    assignment_rows = []

    for sector, g in feats.groupby("sector"):
        g = g.dropna(subset=FEATURE_COLS).reset_index(drop=True)
        n = len(g)
        log.info(f"\n--- {sector} (n={n}) ---")

        X = StandardScaler().fit_transform(g[FEATURE_COLS].values)
        rng = np.random.default_rng(RANDOM_SEED)

        results_this_sector = {}
        for k in K_RANGE:
            ref_labels, ari_mean, ari_std = bootstrap_ari(X, k, rng)
            sil = silhouette_score(X, ref_labels)
            results_this_sector[k] = {"labels": ref_labels, "silhouette": sil,
                                       "ari_mean": ari_mean, "ari_std": ari_std}
            stability_rows.append({"sector": sector, "n": n, "k": k, "silhouette": sil,
                                     "ari_mean": ari_mean, "ari_std": ari_std,
                                     "stable": ari_mean >= ARI_STABILITY_THRESHOLD})
            log.info(f"  k={k}: silhouette={sil:.3f}, bootstrap ARI={ari_mean:.3f} (+-{ari_std:.3f}) "
                      f"{'STABLE' if ari_mean >= ARI_STABILITY_THRESHOLD else 'unstable'}")

        stable_ks = [k for k, r in results_this_sector.items() if r["ari_mean"] >= ARI_STABILITY_THRESHOLD]
        if not stable_ks:
            log.warning(f"  -> {sector}: ไม่มี k ไหนเสถียรเลย (ARI < {ARI_STABILITY_THRESHOLD} ทุก k) "
                        f"— สรุปว่า {sector} ไม่มี pattern ที่จับได้จาก price-path shape นี้")
            continue

        best_k = max(stable_ks, key=lambda k: results_this_sector[k]["silhouette"])
        log.info(f"  -> เลือก k={best_k} (silhouette สูงสุดในกลุ่มที่เสถียร)")

        g["cluster_k"] = best_k
        g["cluster_label"] = results_this_sector[best_k]["labels"]
        g["silhouette"] = results_this_sector[best_k]["silhouette"]
        g["ari_mean"] = results_this_sector[best_k]["ari_mean"]
        assignment_rows.append(g)

    stability_df = pd.DataFrame(stability_rows)
    stability_df.to_csv(OUT_STABILITY, index=False)

    if assignment_rows:
        assignments_df = pd.concat(assignment_rows, ignore_index=True)
    else:
        assignments_df = pd.DataFrame(columns=list(feats.columns) + ["cluster_k", "cluster_label",
                                                                       "silhouette", "ari_mean"])
    assignments_df.to_csv(OUT_ASSIGNMENTS, index=False)

    log.info("\n" + "=" * 60)
    log.info("SUMMARY — Phase E3")
    log.info("=" * 60)
    stable_sectors = sorted(assignments_df["sector"].unique()) if len(assignments_df) else []
    unstable_sectors = sorted(set(feats["sector"].unique()) - set(stable_sectors))
    log.info(f"Sector ที่มี cluster เสถียร ({len(stable_sectors)}): {stable_sectors}")
    log.info(f"Sector ที่ไม่มี cluster เสถียรเลย ({len(unstable_sectors)}): {unstable_sectors}")
    log.info(f"Saved -> {OUT_STABILITY}")
    log.info(f"Saved -> {OUT_ASSIGNMENTS}")
    return stability_df, assignments_df


if __name__ == "__main__":
    main()
