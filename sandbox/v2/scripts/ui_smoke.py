"""
UI smoke test ด้วย Playwright (headless Chromium): เปิดทุกหน้า, รันจาก UI จนจบ, บันทึก, เปิดผล, หน้าหุ้น, compare
เก็บ console error ทั้งหมด + screenshot ลง sandbox/v2/screenshots/

    python3 -m sandbox.v2.scripts.ui_smoke            # เปิด server ของตัวเองที่ port 5095 (เปลี่ยนได้ด้วย env UI_PORT)
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
    errors, created, created_news = [], [], []
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
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "01_pipeline.jpg"), full_page=True)

            # เปิด B stub (กรอง) + C rulebase (กรอง) ผ่าน UI
            pg.click(".box.B .seg button[data-mode=on]")
            pg.click(".box.C .seg button[data-mode=on]")
            pg.wait_for_timeout(1200)
            pg.fill("#run-name", "UI smoke: A1 + B stub + C rb03 + EW")
            pg.click("button.run-btn")
            pg.wait_for_timeout(1500)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "02_running.jpg"), full_page=False)
            pg.wait_for_selector("#view-result", timeout=180000)
            pg.wait_for_timeout(800)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "03_pipeline_done.jpg"), full_page=True)

            pg.click("#view-result")
            pg.wait_for_selector(".hero .metric", timeout=30000)
            pg.wait_for_timeout(2500)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "04_results_run.jpg"), full_page=True)
            pg.fill("#save-name", "UI smoke run")
            pg.click("#save-btn")
            pg.wait_for_function("location.hash.startsWith('#/results/exp/')", timeout=20000)
            exp_id = pg.evaluate("location.hash.split('/').pop()")
            created.append(exp_id)
            pg.wait_for_selector(".hero .metric", timeout=30000)
            pg.wait_for_timeout(2500)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "05_results_saved.jpg"), full_page=True)

            # คลิก trade แรก → หน้าหุ้น
            pg.locator("table.t tbody tr td a").first.click()
            pg.wait_for_function("() => [...document.querySelectorAll('.stock-chart canvas')].some(c => c.width > 100)", timeout=20000)  # canvas ตัวแรกของ lightweight-charts กว้าง 0 เสมอ
            pg.wait_for_timeout(1500)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "06_stock.jpg"), full_page=True)

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
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "07_gallery.jpg"), full_page=True)
            pg.goto(f"{base}/#/compare?ids={exp_id},{exp2}")
            pg.wait_for_timeout(2500)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "08_compare.jpg"), full_page=True)
            for name in ("registry", "about"):
                pg.goto(f"{base}/#/{name}")
                pg.wait_for_timeout(1200)
                pg.screenshot(type="jpeg", quality=72, path=str(OUT / f"09_{name}.jpg"), full_page=True)
            # held-out run → ต้องเห็น badge HELD-OUT + แรเงาแดงบนกราฟ
            hj = requests.post(base + "/api/jobs", json={"name": "UI smoke held-out", "condition": {"id": "hold_SPY"},
                                                         "start": "2023-01-03", "end": "2023-12-29",
                                                         "held_out": {"enabled": True, "confirm": cfg.HELD_OUT_CONFIRM_TEXT}}).json()["id"]
            for _ in range(120):
                if requests.get(f"{base}/api/jobs/{hj}").json()["status"] == "done":
                    break
                time.sleep(0.5)
            pg.goto(f"{base}/#/results/run/{hj}")
            pg.wait_for_selector(".badge.held_out", timeout=20000)
            pg.wait_for_timeout(2000)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "11_results_held_out.jpg"), full_page=False)
            # W7: @mention + auto-detect + macro + ตลาดปิด + mini chart + บันทึก + CSV
            pg.goto(f"{base}/#/news")
            pg.wait_for_selector("#news-headline", timeout=20000)
            pg.fill("input[type=date][x-model=date]", "2023-03-04")  # วันเสาร์
            pg.click("#news-headline")
            pg.keyboard.type("@nvi")
            pg.wait_for_selector(".mention-drop .item", timeout=5000)
            pg.keyboard.press("Enter")
            pg.keyboard.type("rallies as Apple gains; Fed holds rates")
            pg.wait_for_timeout(1200)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "10_news.jpg"), full_page=True)
            pg.click(".suggest button.primary")  # ยืนยัน Apple
            pg.wait_for_timeout(1500)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "10b_news_confirmed.jpg"), full_page=True)
            ids0 = {n["id"] for n in requests.get(base + "/api/news").json()}  # /api/news คืนล่าสุด ≤ 300 แถว → เทียบ id ไม่ใช่จำนวน
            pg.click("#news-save")
            pg.wait_for_timeout(1000)
            saved = requests.get(base + "/api/news").json()
            assert saved and saved[0]["id"] not in ids0, "บันทึกข่าวไม่สำเร็จ"
            new = saved[0]
            assert new["tickers"] == ["AAPL", "NVDA"] and new["source"] == "manual", new
            assert new["effective_date"] == "2023-03-06", new  # เสาร์ → จันทร์
            created_news.append(new["id"])
            csvp = OUT.parent / "cache" / "ui_smoke_news.csv"
            csvp.parent.mkdir(exist_ok=True)
            csvp.write_text("date,title\n2023-01-10,Exxon Mobil and Chevron climb as crude jumps\n2023-02-01,Fed raises rates by 25bp\n")
            pg.set_input_files(".dropzone input[type=file]", str(csvp))
            pg.wait_for_function("document.body.innerText.includes('แถวที่จะบันทึก')", timeout=10000)
            pg.wait_for_timeout(800)
            pg.screenshot(type="jpeg", quality=72, path=str(OUT / "10c_news_csv.jpg"), full_page=True)
            b.close()
    except Exception:
        print("errors so far:", *errors[:20], sep="\n  ")
        raise
    finally:
        keep = os.environ.get("UI_KEEP") == "1"
        if not keep:
            for e in created:
                requests.delete(f"{base}/api/experiments/{e}?confirm={e}")
            for n in created_news:
                requests.delete(f"{base}/api/news/{n}")
        srv.terminate()
        srv.wait(5)
    print(f"console/page errors: {len(errors)}")
    for e in errors:
        print("  ", e[:400])
    print("screenshots:", ", ".join(sorted(x.name for x in OUT.glob("*.jpg"))))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
