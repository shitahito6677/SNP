"""condition พัง / วนลูป → job fail อ่านง่าย และ server ยังตอบได้ (รัน server จริงใน process แยก)"""
import os
import subprocess
import sys
import time

import pytest
import requests

from sandbox.v2 import config as cfg

PORT = 5099
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server():
    env = dict(os.environ, SANDBOX_V2_PORT=str(PORT))
    p = subprocess.Popen([sys.executable, "-m", "sandbox.v2.server"], cwd=cfg.REPO, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            requests.get(BASE + "/api/registry", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.5)
    yield
    p.terminate()
    p.wait(5)


def submit(src, **kw):
    body = {"start": "2022-01-03", "end": "2022-02-28", "condition": {"source": src}, **kw}
    r = requests.post(BASE + "/api/jobs", json=body, timeout=30)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def wait(job_id, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = requests.get(f"{BASE}/api/jobs/{job_id}", timeout=10).json()
        if d["status"] not in ("queued", "running"):
            return d
        time.sleep(0.5)
    raise AssertionError("job ไม่จบในเวลา")


def test_condition_exception_fails_job_with_traceback(server):
    src = 'NAME = "boom"\nDESCRIPTION = "x"\ndef decide(ctx):\n    x = {}\n    return x["missing"]\n'
    d = wait(submit(src))
    assert d["status"] == "failed"
    assert "KeyError" in d["error"] and "<condition>" in (d["traceback"] or "")
    assert requests.get(BASE + "/api/registry", timeout=10).status_code == 200


def test_infinite_loop_is_killed_and_server_keeps_answering(server):
    src = 'NAME = "loop"\nDESCRIPTION = "x"\ndef decide(ctx):\n    while True:\n        pass\n'
    job = submit(src)
    time.sleep(2)
    r = requests.get(BASE + "/api/registry", timeout=10)  # ระหว่าง job วนลูปอยู่
    assert r.status_code == 200 and r.json()["models"]["A"]
    d = wait(job, timeout=cfg.DECIDE_TIMEOUT_SEC + 60)
    assert d["status"] == "failed" and "ไม่ตอบภายใน" in d["error"]


def test_bad_weights_fail_clearly(server):
    src = 'NAME = "lev"\nDESCRIPTION = "x"\ndef decide(ctx):\n    return {"SPY": 2.0}\n'
    d = wait(submit(src))
    assert d["status"] == "failed" and "> 1.0" in d["error"]


def test_held_out_rejected_by_api(server):
    r = requests.post(BASE + "/api/jobs", json={"end": "2024-01-31", "condition": {"id": "hold_SPY"}}, timeout=30)
    assert r.status_code == 403 and r.json()["kind"] == "held_out"


def test_cancel(server):
    src = 'NAME = "slow"\nDESCRIPTION = "x"\nimport time\ndef decide(ctx):\n    time.sleep(0.5)\n    return {}\n'
    job = submit(src)
    time.sleep(3)
    requests.post(f"{BASE}/api/jobs/{job}/cancel", timeout=10)
    d = wait(job, timeout=30)
    assert d["status"] == "cancelled"
