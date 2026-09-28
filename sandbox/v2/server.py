"""
Sandbox v2 "Pipeline Lab" — Flask server

รัน (จาก repo root):  python3 -m sandbox.v2.server
⚠️ bind 127.0.0.1 เท่านั้น — หน้าเว็บนี้รันโค้ด Python ที่ผู้ใช้เขียนได้ ห้ามเปิดผ่าน ngrok/tunnel/LAN
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from sandbox.v2 import condition_registry, config as cfg, experiments_store as xs, jobs, registry
from werkzeug.exceptions import HTTPException

LOG_FILE = cfg.V2 / "logs" / "server.log"


def _logger() -> logging.Logger:
    """traceback เต็มของทุก error → stderr + sandbox/v2/logs/server.log (gitignored)"""
    lg = logging.getLogger("sandbox.v2.server")
    if not lg.handlers:
        lg.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        for h in (logging.StreamHandler(), RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")):
            h.setFormatter(fmt)
            lg.addHandler(h)
        lg.propagate = False
    return lg


log = _logger()


def fail(e: BaseException, message: str, status: int = 500):
    """log traceback เต็มฝั่ง server แล้วคืนข้อความไทยที่อ่านรู้เรื่อง + error_id ไว้ค้นใน log — ห้ามคืน 500 ดิบ"""
    eid = uuid.uuid4().hex[:8]
    log.error("error_id=%s %s %s → %s: %s\n%s", eid, request.method, request.full_path, type(e).__name__, e,
              "".join(traceback.format_exception(type(e), e, e.__traceback__)))
    return jsonify({"error": f"{message} (รหัสอ้างอิง {eid} — ดูรายละเอียดใน {LOG_FILE.relative_to(cfg.REPO)})",
                    "kind": "server", "error_id": eid, "detail": f"{type(e).__name__}: {e}"[:500]}), status


def _asset_version() -> str:
    """cache-busting ของ static (mtime ล่าสุดของ app.js/app.css)"""
    fs = [cfg.V2 / "static" / n for n in ("app.css", "app.js", "pipeline.js", "results.js", "stock.js", "news.js")]
    return str(int(max((f.stat().st_mtime for f in fs if f.exists()), default=0)))


def rebuild_manual_labels():
    """B version จากข่าว manual (model_B/export/manual-labels*) — build ใหม่ทุกครั้งที่ข่าวเปลี่ยน; พังแล้วไม่ล้มทั้ง request"""
    from sandbox.v2 import manual_labels
    try:
        return manual_labels.build()
    except Exception:  # noqa: BLE001
        log.exception("rebuild manual-labels failed")
        return None


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.json.ensure_ascii = False
    rebuild_manual_labels()

    @app.errorhandler(Exception)
    def on_error(e):
        """ตาข่ายสุดท้าย: exception ที่ endpoint ไม่ได้จับเอง → JSON ภาษาไทย (ไม่ใช่หน้า 500 HTML ดิบ)"""
        if isinstance(e, HTTPException):
            th = {400: "คำขอไม่ถูกต้อง", 404: "ไม่พบหน้า/ข้อมูลที่ขอ", 405: "method ไม่ถูกต้อง", 413: "ไฟล์ใหญ่เกินไป"}
            if not request.path.startswith("/api/"):
                return e
            return jsonify({"error": f"{th.get(e.code, 'คำขอผิดพลาด')} ({e.code}: {e.description})", "kind": "http"}), e.code
        return fail(e, f"เกิดข้อผิดพลาดภายใน server ที่ {request.path}")

    @app.get("/api/registry")
    def api_registry():
        snap = registry.snapshot()
        snap["conditions"] = condition_registry.list_conditions()
        return jsonify(snap)

    @app.post("/api/registry/rescan")
    def api_rescan():
        rebuild_manual_labels()
        snap = registry.scan()
        snap["conditions"] = condition_registry.list_conditions()
        return jsonify(snap)

    @app.get("/api/conditions/<cid>")
    def api_condition(cid):
        try:
            return jsonify({"id": cid, "source": condition_registry.source(cid)})
        except (KeyError, ValueError) as e:
            return jsonify({"error": str(e)}), 404

    @app.post("/api/conditions")
    def api_condition_save():
        body = request.get_json(force=True)
        try:
            p = condition_registry.save_new(body.get("id", ""), body.get("source", ""))
        except FileExistsError as e:
            return jsonify({"error": str(e)}), 409
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "file": str(p.relative_to(cfg.REPO))})

    # ------------------------------------------------------------ jobs
    def _prepare(body, allow_legacy=False):
        from sandbox.v2 import engine
        conf, warnings = engine.normalize_config(body, allow_legacy=allow_legacy)
        warnings += engine.coverage_warnings(conf)
        return conf, warnings

    def _err(e):
        from sandbox.v2 import engine, prices
        if isinstance(e, engine.LegacyConfigError):
            return jsonify({"error": str(e), "kind": "legacy", "notes": e.notes}), 409
        if isinstance(e, prices.HeldOutError):
            return jsonify({"error": str(e), "kind": "held_out"}), 403
        if isinstance(e, (engine.ConfigError, KeyError, ValueError)):
            return jsonify({"error": str(e).strip("'\""), "kind": "config"}), 400
        raise e

    @app.post("/api/preflight")
    def api_preflight():
        try:
            conf, warnings = _prepare(request.get_json(force=True))
        except Exception as e:  # noqa: BLE001
            return _err(e)
        from sandbox.v2 import engine
        sc = conf["scope"]
        try:
            stats = engine.box_stats(conf)
        except Exception:  # noqa: BLE001 — ตัวเลขบนกล่องเป็นแค่ภาพประกอบ ไม่ควรทำให้ preflight ล้ม
            log.exception("box_stats failed")
            stats = {}
        return jsonify({"ok": True, "warnings": warnings, "held_out_touched": conf["held_out"]["touched"], "box_stats": stats,
                        "scope": {"mode": sc["mode"], "label": engine.scope_label(sc), "sectors": sc["sectors"], "tickers": sc["tickers"],
                                  "n_members": len(sc["members"]) if "members" in sc else None}})

    @app.post("/api/jobs")
    def api_job_submit():
        try:
            conf, warnings = _prepare(request.get_json(force=True))
        except Exception as e:  # noqa: BLE001
            return _err(e)
        job_id = jobs.submit(conf, warnings)
        return jsonify({"id": job_id, "warnings": warnings}), 201

    @app.get("/api/jobs")
    def api_jobs():
        return jsonify(jobs.list_jobs())

    @app.get("/api/jobs/<job_id>")
    def api_job(job_id):
        d = jobs.get(job_id, since=int(request.args.get("since", 0)))
        if d is None:
            return jsonify({"error": "ไม่พบ job"}), 404
        d.pop("config", None)
        return jsonify(d)

    @app.post("/api/jobs/<job_id>/cancel")
    def api_job_cancel(job_id):
        if jobs.get(job_id, with_logs=False) is None:
            return jsonify({"error": "ไม่พบ job"}), 404
        jobs.cancel(job_id)
        threading.Thread(target=jobs.kill_after_grace, args=(job_id,), daemon=True).start()
        return jsonify({"ok": True})

    @app.get("/api/jobs/<job_id>/stream")
    def api_job_stream(job_id):
        def gen():
            since, last = 0, None
            while True:
                d = jobs.get(job_id, since=since)
                if d is None:
                    yield "event: error\ndata: {\"error\": \"ไม่พบ job\"}\n\n"
                    return
                if d["logs"]:
                    since = d["logs"][-1]["rowid"]
                d.pop("config", None)
                key = (d["status"], d["stage"], d["pct"], d["eta_sec"], len(d["logs"]))
                if key != last:
                    last = key
                    yield f"data: {json.dumps(d, ensure_ascii=False, default=str)}\n\n"
                if d["status"] not in ("queued", "running"):
                    return
                time.sleep(0.5)
        return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------ meta / stock / validate
    @app.get("/")
    def index():
        return render_template("index.html", v=_asset_version())

    @app.get("/api/meta")
    def api_meta():
        from sandbox.v2 import news, prices
        man = prices.manifest()
        tickers = [{"t": t, "name": r.get("name") or t, "sector": r.get("sector") or "Unknown", "status": r.get("status"),
                    "kind": r.get("kind")} for t, r in sorted(man["tickers"].items()) if r.get("status") in ("ok", "partial")]
        return jsonify({
            "config": {"price_start": cfg.PRICE_START, "default_end": cfg.DEFAULT_END, "held_out_start": cfg.HELD_OUT_START,
                       "confirm_text": cfg.HELD_OUT_CONFIRM_TEXT, "capital": cfg.INITIAL_CAPITAL, "cost": cfg.TRANSACTION_COST,
                       "execution": cfg.EXECUTION, "decide_timeout": cfg.DECIDE_TIMEOUT_SEC},
            "latest_trading_day": man.get("latest_trading_day"), "counts": man.get("counts"),
            "data_hash": man.get("data_hash"), "sp500_snapshot_date": man.get("sp500_snapshot_date"),
            "sector_etfs": cfg.SECTOR_ETFS, "tickers": tickers,
            "news_labels": [[k, v] for k, v in sorted(news.LABELS.items())],  # label ข่าว manual 5 ระดับ (ลำดับ -2 → +2)
            "vendor": {"plotly": (cfg.V2 / "static/vendor/plotly.min.js").exists(),
                       "monaco": (cfg.V2 / "static/vendor/monaco/vs/loader.js").exists()},
        })

    @app.get("/api/stocks/gallery")
    def api_stock_gallery():
        """หุ้นที่มีราคาครบ (status ok) สำหรับ gallery หน้าหุ้นรายตัว — logo = มีไฟล์ใน cache แล้ว (ไม่ยิง network)"""
        from sandbox.v2 import news, prices
        counts = news.ticker_counts()
        rows = [{"t": t, "name": r.get("name") or t, "sector": r.get("sector") or "Unknown",
                 "etf": cfg.SECTOR_ETFS.get(r.get("sector") or ""), "news": counts.get(t, 0),
                 "logo": (cfg.LOGOS_DIR / f"{t}.png").exists()}
                for t, r in sorted(prices.manifest()["tickers"].items()) if r.get("status") == "ok" and r.get("kind") == "stock"]
        return jsonify({"tickers": rows, "n": len(rows)})

    @app.get("/api/stock/<ticker>")
    def api_stock(ticker):
        from sandbox.v2 import stock_view
        a = request.args
        t = ticker.strip().upper().replace(".", "-")
        try:
            return jsonify(stock_view.build(t, a.get("kind"), a.get("id"), a.get("start"), a.get("end"),
                                            {m: a.get(m) for m in "ABC" if a.get(m)}))
        except stock_view.StockError as e:  # ข้อความไทยที่ตั้งใจแสดงผู้ใช้ (ไม่พบ ticker / ไม่มีราคา / วันที่ผิด / ไม่พบการทดลอง)
            log.info("stock %s: %s", t, e)
            return jsonify({"error": str(e), "kind": e.kind, "ticker": t}), e.status
        except Exception as e:  # noqa: BLE001
            return fail(e, f"โหลดหน้าหุ้น {t} ไม่สำเร็จเพราะข้อผิดพลาดภายใน")

    @app.post("/api/validate")
    def api_validate():
        body = request.get_json(force=True)
        env = dict(os.environ, PYTHONHASHSEED="0")
        try:
            p = subprocess.run([sys.executable, "-m", "sandbox.v2.dryrun"], cwd=cfg.REPO, env=env, capture_output=True,
                               text=True, input=json.dumps(body), timeout=cfg.DECIDE_TIMEOUT_SEC + 60)
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "validate เกินเวลา — condition อาจวนลูปไม่จบ"})
        if "@@RESULT@@" not in p.stdout:
            return jsonify({"ok": False, "error": "validate ล้มเหลว", "traceback": (p.stderr or "")[-3000:]})
        return Response(p.stdout.split("@@RESULT@@", 1)[1], mimetype="application/json")

    # ------------------------------------------------------------ manual news (source="manual")
    @app.post("/api/news/detect")
    def api_news_detect():
        from sandbox.v2 import news
        b = request.get_json(force=True)
        out = news.detect(b.get("text", ""))
        if b.get("date"):
            try:
                out["date_info"] = news.trading_day_info(b["date"])
            except (ValueError, TypeError):
                out["date_info"] = None
        return jsonify(out)

    @app.get("/api/news")
    def api_news_list():
        from sandbox.v2 import news
        return jsonify(news.list_news())

    @app.get("/api/news/methods")
    def api_news_methods():
        """จำนวนข่าวตามวิธี label + ชุดข่าวที่ยังไม่ระบุ (ให้ผู้ใช้ระบุ hindsight / real-time เอง)"""
        from sandbox.v2 import news
        return jsonify(dict(news.method_summary(), methods=[[k, v] for k, v in news.LABEL_METHODS.items()]))

    @app.post("/api/news/label_method")
    def api_news_set_method():
        from sandbox.v2 import news
        b = request.get_json(force=True, silent=True) or {}
        try:
            n = news.set_label_method(b.get("ids") or [], b.get("method"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if n:
            rebuild_manual_labels()
        return jsonify({"updated": n})

    @app.post("/api/news")
    def api_news_add():
        from sandbox.v2 import news
        try:
            row = news.add(request.get_json(force=True))
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400
        rebuild_manual_labels()
        return jsonify(row), 201

    @app.delete("/api/news/<nid>")
    def api_news_delete(nid):
        from sandbox.v2 import news
        if not news.delete(nid):
            return jsonify({"error": "ไม่พบข่าว"}), 404
        rebuild_manual_labels()
        return jsonify({"ok": True})

    @app.post("/api/news/csv/preview")
    def api_news_csv_preview():
        from sandbox.v2 import news
        try:
            b = request.get_json(force=True, silent=True)
            if not isinstance(b, dict):
                return jsonify({"error": "อ่านไฟล์ไม่ได้: ส่งข้อมูลมาไม่ถูกรูปแบบ (ต้องเป็น JSON {text, mapping})"}), 400
            return jsonify(news.csv_preview(b.get("text", ""), b.get("mapping") or None))
        except ValueError as e:  # ข้อความไทยจาก csv_preview (ไฟล์ว่าง/ไม่มีหัวตาราง/encoding ผิด/mapping ผิด)
            log.info("csv preview rejected: %s", e)
            return jsonify({"error": str(e), "kind": "csv"}), 400
        except Exception as e:  # noqa: BLE001
            return fail(e, "อ่านไฟล์ CSV ไม่สำเร็จเพราะข้อผิดพลาดภายใน")

    @app.post("/api/news/csv/commit")
    def api_news_csv_commit():
        from sandbox.v2 import news
        saved, errors = [], []
        b = request.get_json(force=True, silent=True) or {}
        for r in b.get("rows", []) if isinstance(b, dict) else []:
            if not isinstance(r, dict) or not r.get("include"):
                continue
            r = dict(r, effective_date=None)  # ผู้ใช้อาจแก้วันที่ใน preview → คำนวณวันที่มีผลใหม่เสมอ
            try:
                saved.append(news.add(r))
            except (ValueError, KeyError) as e:
                errors.append({"row": r.get("row"), "error": str(e).strip("'\"")})
            except Exception as e:  # noqa: BLE001 — แถวเดียวพังไม่ให้ทั้งไฟล์พัง
                resp, _ = fail(e, "บันทึกแถวนี้ไม่สำเร็จ")
                errors.append({"row": r.get("row"), "error": resp.get_json()["error"]})
        if saved:
            rebuild_manual_labels()
        return jsonify({"saved": len(saved), "errors": errors, "ids": [x["id"] for x in saved]})

    # ------------------------------------------------------------ results / experiments
    def _result_dir(kind, rid):
        if kind == "run":
            d = jobs.get(rid, with_logs=False)
            if d is None or d["status"] != "done":
                raise KeyError("run นี้ยังไม่เสร็จหรือไม่พบ")
            return Path(d["result_dir"])
        return xs.path(rid)

    @app.get("/api/results/<kind>/<rid>")
    def api_result(kind, rid):
        try:
            if kind == "exp":
                return jsonify(xs.load(rid))
            out = xs.load_dir(_result_dir("run", rid))
            out["job_id"] = rid
            return jsonify(out)
        except KeyError as e:
            return jsonify({"error": str(e).strip("'\"")}), 404

    @app.get("/api/results/<kind>/<rid>/trades")
    def api_result_trades(kind, rid):
        try:
            d = _result_dir(kind, rid)
        except KeyError as e:
            return jsonify({"error": str(e).strip("'\"")}), 404
        a = request.args
        return jsonify(xs.trades(d, a.get("q", ""), a.get("side", ""), a.get("ticker", ""),
                                 int(a.get("offset", 0)), min(int(a.get("limit", 200)), 2000)))

    @app.post("/api/experiments")
    def api_exp_save():
        body = request.get_json(force=True)
        try:
            exp_id = xs.save(_result_dir("run", body.get("job_id", "")), body.get("name", ""))
        except (KeyError, FileNotFoundError) as e:
            return jsonify({"error": str(e).strip("'\"")}), 400
        return jsonify({"id": exp_id}), 201

    @app.get("/api/experiments")
    def api_exp_list():
        return jsonify(xs.list_all())

    @app.delete("/api/experiments/<exp_id>")
    def api_exp_delete(exp_id):
        try:
            xs.delete(exp_id, request.args.get("confirm", ""))
        except KeyError as e:
            return jsonify({"error": str(e).strip("'\"")}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True})

    @app.get("/api/experiments/<exp_id>/bundle")
    def api_exp_bundle(exp_id):
        try:
            data = xs.bundle(exp_id)
        except KeyError as e:
            return jsonify({"error": str(e).strip("'\"")}), 404
        return Response(data, mimetype="application/zip",
                        headers={"Content-Disposition": f"attachment; filename={exp_id}.zip"})

    @app.post("/api/experiments/<exp_id>/rerun")
    def api_exp_rerun(exp_id):
        force = request.args.get("force") == "1"  # config แบบเดิม (เกณฑ์กรองในกล่อง) → ต้องยืนยันก่อน เพราะผลจะต่างจากเดิม
        try:
            d = xs.path(exp_id)
        except KeyError as e:
            return jsonify({"error": str(e).strip("'\"")}), 404
        conf = json.loads((d / "config.json").read_text())
        conf["condition"] = {"id": conf["condition"].get("id"),
                             "source": (d / "condition_snapshot.py").read_text(encoding="utf-8")}
        if conf["held_out"].get("touched"):  # ผลนี้แตะ held-out ไปแล้ว — รันซ้ำ config เดิมไม่เพิ่มข้อมูลใหม่
            conf["held_out"] = {"enabled": True, "confirm": cfg.HELD_OUT_CONFIRM_TEXT}
        try:
            conf2, warnings = _prepare(conf, allow_legacy=force)
        except Exception as e:  # noqa: BLE001
            return _err(e)
        conf2["name"] = f"re-run of {exp_id}"
        return jsonify({"job_id": jobs.submit(conf2, warnings)}), 201

    @app.get("/api/experiments/<exp_id>/rerun/<job_id>")
    def api_exp_rerun_diff(exp_id, job_id):
        try:
            return jsonify(xs.diff_runs(xs.path(exp_id), _result_dir("run", job_id)))
        except KeyError as e:
            return jsonify({"error": str(e).strip("'\"")}), 404

    @app.get("/api/compare")
    def api_compare():
        ids = [x for x in request.args.get("ids", "").split(",") if x]
        try:
            return jsonify(xs.compare(ids))
        except KeyError as e:
            return jsonify({"error": str(e).strip("'\"")}), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=cfg.HOST, port=cfg.PORT, debug=False, threaded=True)
