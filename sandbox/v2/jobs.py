"""
Job runner — 1 run = 1 process แยก (`python3 -m sandbox.v2.jobs run <job_id>`) สถานะเก็บใน SQLite (jobs.db)

server ไม่เคย exec โค้ด condition เอง: job process → condition process (condition_worker) อีกชั้น
ETA มาจาก throughput จริงของ simulator (วันที่ประมวลผลแล้ว ÷ เวลาที่ใช้)
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sandbox.v2 import config as cfg

RUNS_DIR = cfg.CACHE_DIR / "runs"
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, status TEXT, stage TEXT, pct REAL, eta_sec REAL, message TEXT,
  created_at TEXT, started_at TEXT, updated_at TEXT, finished_at TEXT,
  config TEXT, warnings TEXT, error TEXT, traceback TEXT, pid INTEGER, cancel_requested INTEGER DEFAULT 0,
  result_dir TEXT, summary TEXT
);
CREATE TABLE IF NOT EXISTS job_logs (job_id TEXT, ts TEXT, level TEXT, msg TEXT);
CREATE INDEX IF NOT EXISTS job_logs_id ON job_logs(job_id);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    cfg.JOBS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cfg.JOBS_DB, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def update(job_id, **f):
    f["updated_at"] = _now()
    with db() as con:
        con.execute(f"UPDATE jobs SET {', '.join(k + '=?' for k in f)} WHERE id=?", [*f.values(), job_id])


def log(job_id, msg, level="info"):
    with db() as con:
        con.execute("INSERT INTO job_logs VALUES (?,?,?,?)", (job_id, _now(), level, str(msg)[:2000]))


def get(job_id, with_logs=True, since=0) -> dict | None:
    with db() as con:
        r = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if r is None:
            return None
        d = dict(r)
        for k in ("config", "warnings", "summary"):
            d[k] = json.loads(d[k]) if d.get(k) else None
        if with_logs:
            rows = con.execute("SELECT rowid, ts, level, msg FROM job_logs WHERE job_id=? AND rowid>? ORDER BY rowid",
                               (job_id, since)).fetchall()
            d["logs"] = [dict(x) for x in rows]
    _check_alive(d)
    return d


def list_jobs(limit=30) -> list:
    with db() as con:
        rows = con.execute("SELECT id, status, stage, pct, created_at, finished_at, config, error FROM jobs "
                           "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        c = json.loads(d.pop("config") or "{}")
        d["name"] = c.get("name")
        out.append(d)
    return out


def _check_alive(d):
    """process ตายโดยไม่ได้อัปเดตสถานะ (เช่น ถูก kill) → mark failed"""
    if d["status"] in ("running", "queued") and d.get("pid"):
        try:
            os.kill(d["pid"], 0)
        except ProcessLookupError:
            update(d["id"], status="failed", error="process ของ job หยุดทำงานโดยไม่ได้แจ้งสถานะ", finished_at=_now())
            d["status"] = "failed"
        except PermissionError:
            pass


def submit(conf: dict, warnings: list) -> str:
    job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    out = RUNS_DIR / job_id
    with db() as con:
        con.execute("INSERT INTO jobs (id, status, stage, pct, created_at, updated_at, config, warnings, result_dir) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (job_id, "queued", "load", 0.0, _now(), _now(), json.dumps(conf, ensure_ascii=False),
                     json.dumps(warnings, ensure_ascii=False), str(out)))
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    logf = open(RUNS_DIR / f"{job_id}.stderr.log", "w")
    p = subprocess.Popen([sys.executable, "-m", "sandbox.v2.jobs", "run", job_id], cwd=cfg.REPO,
                         stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    update(job_id, pid=p.pid)
    return job_id


def cancel(job_id):
    update(job_id, cancel_requested=1)
    d = get(job_id, with_logs=False)
    log(job_id, "ผู้ใช้กดยกเลิก", "warn")
    return d


def kill_after_grace(job_id, grace=5.0):
    """ถ้า job ไม่หยุดเองใน grace วินาที (เช่น ติดอยู่ใน decide) → kill ทั้ง process group"""
    t0 = time.time()
    while time.time() - t0 < grace:
        d = get(job_id, with_logs=False)
        if d is None or d["status"] not in ("running", "queued"):
            return
        time.sleep(0.25)
    d = get(job_id, with_logs=False)
    if d and d.get("pid"):
        try:
            os.killpg(d["pid"], signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        update(job_id, status="cancelled", finished_at=_now(), message="ยกเลิก (kill)")


# ------------------------------------------------------------------ job process

def _run(job_id):
    from sandbox.v2 import engine  # import ช้า → ทำใน process ของ job

    d = get(job_id, with_logs=False)
    conf = d["config"]
    update(job_id, status="running", started_at=_now(), pid=os.getpid())
    last = {"t": 0.0}

    def progress(stage, pct, eta, msg):
        now = time.time()
        if now - last["t"] < 0.3 and pct < 100:
            return
        last["t"] = now
        f = {"stage": stage, "pct": round(float(pct), 2), "eta_sec": None if eta is None else round(float(eta), 1)}
        if msg:
            f["message"] = msg
        update(job_id, **f)

    def cancelled():
        with db() as con:
            r = con.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(r and r[0])

    try:
        res = engine.run(conf, Path(d["result_dir"]), progress=progress, cancelled=cancelled,
                         log=lambda m: log(job_id, m))
        f = res["metrics"]["full"]
        summary = {k: f["strategy"].get(k) for k in ("total_return", "cagr", "sharpe", "max_dd", "n_trades")}
        summary["spy_total_return"] = f["spy"].get("total_return")
        update(job_id, status="done", pct=100.0, eta_sec=0, finished_at=_now(),
               summary=json.dumps(summary, ensure_ascii=False))
    except engine.Cancelled as e:
        update(job_id, status="cancelled", finished_at=_now(), message=str(e))
    except engine.ConditionError as e:
        log(job_id, f"condition error: {e}", "error")
        update(job_id, status="failed", finished_at=_now(), error=f"Condition error: {e}", traceback=e.tb)
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc()
        log(job_id, f"{type(e).__name__}: {e}", "error")
        update(job_id, status="failed", finished_at=_now(), error=f"{type(e).__name__}: {e}", traceback=tb)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        _run(sys.argv[2])
