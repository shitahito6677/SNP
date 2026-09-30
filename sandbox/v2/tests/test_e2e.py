"""W8 end-to-end: A1 (จริง) + B stub + C rulebase-exp03 → run → save → restart server → load → ตัวเลขตรงกัน"""
import json

import requests

from sandbox.v2 import config as cfg
from sandbox.v2.tests.test_persistence import BASE, start_server, wait


def test_e2e_real_A_stub_B_negative_C():
    body = {"name": "pytest e2e", "stages": {"A": {"mode": "on", "version": "A:A1_r001_Q_LOWACC_overall"},
                                             "B": {"mode": "on", "version": "B:stub"},
                                             "C": {"mode": "on", "version": "C:rulebase-exp03"}},
            "condition": {"id": "equal_weight_A"}}
    p = start_server()
    try:
        r = requests.post(BASE + "/api/jobs", json=body, timeout=30).json()
        assert any("STUB" in w for w in r["warnings"]) and any("NEGATIVE" in w for w in r["warnings"])
        job = r["id"]
        wait(job)
        live = requests.get(f"{BASE}/api/results/run/{job}", timeout=60).json()
        exp = requests.post(BASE + "/api/experiments", json={"job_id": job, "name": "pytest e2e"}, timeout=30).json()["id"]
    finally:
        p.terminate(); p.wait(5)
    p = start_server()
    try:
        got = requests.get(f"{BASE}/api/results/exp/{exp}", timeout=60).json()
        assert got["metrics"] == live["metrics"] and got["equity"] == live["equity"] and got["funnel"] == live["funnel"]
        kinds = {b["kind"] for b in got["badges"]}
        assert {"stub", "negative"} <= kinds and "held_out" not in kinds
        prov = json.loads((cfg.EXPERIMENTS_DIR / exp / "provenance.json").read_text())
        assert set(prov["versions"]) == {"A", "B", "C"} and prov["data_hash"] and prov["git"]["commit"]
        t1 = requests.get(f"{BASE}/api/results/exp/{exp}/trades?limit=5", timeout=30).json()
        assert t1["total"] > 0 and all(any(c.startswith("A:") for c in r["reasons"]) for r in t1["rows"])
        assert requests.delete(f"{BASE}/api/experiments/{exp}?confirm={exp}", timeout=10).status_code == 200
    finally:
        p.terminate(); p.wait(5)
