"""
Sandbox v2 "Pipeline Lab" — Flask server

รัน (จาก repo root):  python3 -m sandbox.v2.server
⚠️ bind 127.0.0.1 เท่านั้น — หน้าเว็บนี้รันโค้ด Python ที่ผู้ใช้เขียนได้ ห้ามเปิดผ่าน ngrok/tunnel/LAN
"""

from __future__ import annotations

from flask import Flask, jsonify, request

from sandbox.v2 import condition_registry, config as cfg, registry


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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=cfg.HOST, port=cfg.PORT, debug=False, threaded=True)
