"""W4: รัน → บันทึก → restart server → เปิดใหม่ → metrics + equity ตรงกัน 100%; re-run ต้องได้ผลเดิม"""
import json
import os
import subprocess
import sys
import time

import pandas as pd
import requests

from sandbox.v2 import config as cfg

PORT = 5097
BASE = f"http://127.0.0.1:{PORT}"


def start_server():
    env = dict(os.environ, SANDBOX_V2_PORT=str(PORT))
    p = subprocess.Popen([sys.executable, "-m", "sandbox.v2.server"], cwd=cfg.REPO, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            requests.get(BASE + "/api/registry", timeout=1)
            return p
        except requests.RequestException:
            time.sleep(0.5)
    raise RuntimeError("server ไม่ขึ้น")


def wait(job):
    for _ in range(300):
        d = requests.get(f"{BASE}/api/jobs/{job}", timeout=10).json()
        if d["status"] not in ("queued", "running"):
            assert d["status"] == "done", d.get("error")
            return d
        time.sleep(0.5)
    raise AssertionError("timeout")


def test_save_restart_reload_identical():
    body = {"name": "pytest persistence", "start": "2022-01-03", "end": "2023-06-30",
            "stages": {"A": {"mode": "on", "version": "A:A1_r001_Q_LOWACC_overall"},
                       "C": {"mode": "on", "version": "C:rulebase-exp03"}},
            "condition": {"id": "follow_A_weights"}}
    p = start_server()
    try:
        job = requests.post(BASE + "/api/jobs", json=body, timeout=30).json()["id"]
        wait(job)
        live = requests.get(f"{BASE}/api/results/run/{job}", timeout=30).json()
        exp = requests.post(BASE + "/api/experiments", json={"job_id": job, "name": "pytest persistence"}, timeout=30).json()["id"]
    finally:
        p.terminate(); p.wait(5)
    p = start_server()  # restart
    try:
        got = requests.get(f"{BASE}/api/results/exp/{exp}", timeout=30).json()
        d = cfg.EXPERIMENTS_DIR / exp
        saved = json.loads((d / "metrics.json").read_text())
        assert got["metrics"] == saved == live["metrics"]  # ทุกตัวเลขตรงกัน
        assert got["equity"] == live["equity"]
        run_eq = pd.read_parquet(cfg.CACHE_DIR / "runs" / job / "equity.parquet")
        assert pd.read_parquet(d / "equity.parquet").equals(run_eq)
        assert got["config"]["name"] == "pytest persistence"
        assert (d / "condition_snapshot.py").read_text() == (cfg.CONDITIONS_DIR / "follow_A_weights.py").read_text()
        assert any(x["id"] == exp for x in requests.get(BASE + "/api/experiments", timeout=10).json())
        # re-run เพื่อตรวจ reproducibility
        rj = requests.post(f"{BASE}/api/experiments/{exp}/rerun", timeout=30).json()["job_id"]
        wait(rj)
        diff = requests.get(f"{BASE}/api/experiments/{exp}/rerun/{rj}", timeout=30).json()
        assert diff["identical"] and diff["equity_identical"], diff
        # ลบต้องยืนยัน
        assert requests.delete(f"{BASE}/api/experiments/{exp}", timeout=10).status_code == 400
        assert requests.delete(f"{BASE}/api/experiments/{exp}?confirm={exp}", timeout=10).status_code == 200
        assert not d.exists()
    finally:
        p.terminate(); p.wait(5)
