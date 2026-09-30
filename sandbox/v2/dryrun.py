"""Validate (dry-run 1 วัน) ใน process แยก — server เรียกด้วย subprocess + timeout: stdin = JSON config, stdout = JSON ผล"""
import json
import sys
import traceback


def main():
    from sandbox.v2 import engine, prices

    body = json.loads(sys.stdin.read())
    try:
        conf, warnings = engine.normalize_config(body["config"])
        out = engine.dry_run(conf, body.get("date"))
        out["ok"], out["warnings"] = True, warnings
    except engine.ConditionError as e:
        out = {"ok": False, "error": str(e), "traceback": e.tb}
    except (engine.ConfigError, prices.HeldOutError, KeyError, ValueError) as e:
        out = {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
    sys.stdout.write("\n@@RESULT@@" + json.dumps(out, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
