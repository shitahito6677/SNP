"""
UI smoke test ด้วย Playwright (headless Chromium): เปิดทุกหน้า, รันจาก UI จนจบ, บันทึก, เปิดผล, หน้าหุ้น, compare
เก็บ console error ทั้งหมด + screenshot ลง sandbox/v2/screenshots/

    python3 -m sandbox.v2.scripts.ui_smoke            # ใช้ server ที่รันอยู่ที่ 127.0.0.1:5060 หรือเปิดใหม่ที่ port 5095
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import requests

from sandbox.v2 import config as cfg

OUT = cfg.V2 / "screenshots"


def main():
    from playwright.sync_api import sync_playwright

    port = int(os.environ.get("UI_PORT", "5095"))
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, SANDBOX_V2_PORT=str(port))
    srv = subprocess.Popen([sys.executable, "-m", "sandbox.v2.server"], cwd=cfg.REPO, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            requests.get(base + "/api/meta", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.5)
    OUT.mkdir(exist_ok=True)
    errors, created = [], []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            pg.on("console", lambda m: m.type == "error" and errors.append(f"[console] {m.text}"))
            pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
            pg.on("requestfailed", lambda r: errors.append(f"[requestfailed] {r.url} {r.failure}"))

            pg.goto(base + "/#/pipeline")
            pg.wait_for_selector(".box.A", timeout=20000)
            pg.wait_for_timeout(2500)  # monaco + preflight
            pg.screenshot(path=str(OUT / "01_pipeline.png"), full_page=True)

            # เปิด B stub (กรอง) + C rulebase (กรอง) ผ่าน UI
            pg.click(".box.B .seg button[data-mode=filter]")
            pg.click(".box.C .seg button[data-mode=filter]")
            pg.wait_for_timeout(1200)
            pg.fill("#run-name", "UI smoke: A1 + B stub + C rb03 + EW")
            pg.click("button.run-btn")
            pg.wait_for_timeout(1500)
            pg.screenshot(path=str(OUT / "02_running.png"), full_page=False)
            pg.wait_for_selector("#view-result", timeout=180000)
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / "03_pipeline_done.png"), full_page=True)

            pg.click("#view-result")
            pg.wait_for_selector(".hero .metric", timeout=30000)
            pg.wait_for_timeout(2500)
            pg.screenshot(path=str(OUT / "04_results_run.png"), full_page=True)
            pg.fill("#save-name", "UI smoke run")
            pg.click("#save-btn")
            pg.wait_for_function("location.hash.startsWith('#/results/exp/')", timeout=20000)
            exp_id = pg.evaluate("location.hash.split('/').pop()")
            created.append(exp_id)
            pg.wait_for_selector(".hero .metric", timeout=30000)
            pg.wait_for_timeout(2500)
            pg.screenshot(path=str(OUT / "05_results_saved.png"), full_page=True)

            # คลิก trade แรก → หน้าหุ้น
            pg.locator("table.t tbody tr td a").first.click()
            pg.wait_for_selector(".stock-chart canvas", timeout=20000)
            pg.wait_for_timeout(1500)
            pg.screenshot(path=str(OUT / "06_stock.png"), full_page=True)

            # รันอีกครั้ง (hold_SPY) เพื่อใช้ compare
            job = requests.post(base + "/api/jobs", json={"name": "UI smoke SPY", "condition": {"id": "hold_SPY"}}).json()["id"]
            for _ in range(120):
                if requests.get(f"{base}/api/jobs/{job}").json()["status"] == "done":
                    break
                time.sleep(0.5)
            exp2 = requests.post(base + "/api/experiments", json={"job_id": job, "name": "UI smoke hold SPY"}).json()["id"]
            created.append(exp2)

            pg.goto(base + "/#/gallery")
            pg.wait_for_selector(".card", timeout=20000)
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / "07_gallery.png"), full_page=True)
            pg.goto(f"{base}/#/compare?ids={exp_id},{exp2}")
            pg.wait_for_timeout(2500)
            pg.screenshot(path=str(OUT / "08_compare.png"), full_page=True)
            for name in ("registry", "about"):
                pg.goto(f"{base}/#/{name}")
                pg.wait_for_timeout(1200)
                pg.screenshot(path=str(OUT / f"09_{name}.png"), full_page=True)
            pg.goto(f"{base}/#/news")
            pg.wait_for_timeout(1500)
            pg.screenshot(path=str(OUT / "10_news.png"), full_page=True)
            b.close()
    except Exception:
        print("errors so far:", *errors[:20], sep="\n  ")
        raise
    finally:
        keep = os.environ.get("UI_KEEP") == "1"
        if not keep:
            for e in created:
                requests.delete(f"{base}/api/experiments/{e}?confirm={e}")
        srv.terminate()
        srv.wait(5)
    print(f"console/page errors: {len(errors)}")
    for e in errors:
        print("  ", e[:400])
    print("screenshots:", ", ".join(sorted(x.name for x in OUT.glob("*.png"))))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
