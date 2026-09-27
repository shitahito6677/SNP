"""
Sandbox v2 "Pipeline Lab" — Flask server

รัน (จาก repo root):  python3 -m sandbox.v2.server
⚠️ bind 127.0.0.1 เท่านั้น — หน้าเว็บนี้รันโค้ด Python ที่ผู้ใช้เขียนได้ ห้ามเปิดผ่าน ngrok/tunnel/LAN
"""

from __future__ import annotations

import json
import threading
import time

from flask import Flask, Response, jsonify, request

from sandbox.v2 import condition_registry, config as cfg, jobs, registry


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.json.ensure_ascii = False

    @app.get("/api/registry")
    def api_registry():
        snap = registry.snapshot()
        snap["conditions"] = condition_registry.list_conditions()
        return jsonify(snap)

    @app.post("/api/registry/rescan")
    def api_rescan():
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
    def _prepare(body):
        from sandbox.v2 import engine
        conf, warnings = engine.normalize_config(body)
        warnings += engine.coverage_warnings(conf)
        return conf, warnings

    def _err(e):
        from sandbox.v2 import engine, prices
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
        return jsonify({"ok": True, "warnings": warnings, "held_out_touched": conf["held_out"]["touched"]})

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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=cfg.HOST, port=cfg.PORT, debug=False, threaded=True)
