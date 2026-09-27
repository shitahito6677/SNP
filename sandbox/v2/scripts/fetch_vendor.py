"""
ดาวน์โหลด front-end library ที่ pin version ไว้ลง sandbox/v2/static/vendor/ (ครั้งเดียว) — หลังจากนั้นเว็บใช้ได้ offline
ห้ามใช้ CDN ตอน runtime

    python3 -m sandbox.v2.scripts.fetch_vendor            # โหลดที่ยังไม่มี + ตรวจ checksum
    python3 -m sandbox.v2.scripts.fetch_vendor --lock     # (เฉพาะตอนเปลี่ยน version) เขียน checksum ใหม่ลง vendor.lock.json

lib เล็ก (Alpine, lightweight-charts, fonts, confetti) ถูก commit ไว้แล้ว; Plotly (4.5 MB) และ Monaco (~18 MB) gitignored
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import urllib.request

from sandbox.v2 import config as cfg

VENDOR = cfg.V2 / "static" / "vendor"
LOCK = VENDOR / "vendor.lock.json"
NPM = "https://cdn.jsdelivr.net/npm/"
FILES = {
    "alpine.min.js": "alpinejs@3.14.1/dist/cdn.min.js",
    "lightweight-charts.js": "lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js",
    "plotly.min.js": "plotly.js-dist-min@2.35.2/plotly.min.js",
    "confetti.js": "canvas-confetti@1.9.3/dist/confetti.browser.js",
    "fonts/plex-thai-thai-400.woff2": "@fontsource/ibm-plex-sans-thai@5.1.0/files/ibm-plex-sans-thai-thai-400-normal.woff2",
    "fonts/plex-thai-thai-600.woff2": "@fontsource/ibm-plex-sans-thai@5.1.0/files/ibm-plex-sans-thai-thai-600-normal.woff2",
    "fonts/plex-thai-latin-400.woff2": "@fontsource/ibm-plex-sans-thai@5.1.0/files/ibm-plex-sans-thai-latin-400-normal.woff2",
    "fonts/plex-thai-latin-600.woff2": "@fontsource/ibm-plex-sans-thai@5.1.0/files/ibm-plex-sans-thai-latin-600-normal.woff2",
    "fonts/jetbrains-mono-400.woff2": "@fontsource/jetbrains-mono@5.1.0/files/jetbrains-mono-latin-400-normal.woff2",
    "fonts/jetbrains-mono-600.woff2": "@fontsource/jetbrains-mono@5.1.0/files/jetbrains-mono-latin-600-normal.woff2",
}
MONACO = ("monaco", "https://registry.npmjs.org/monaco-editor/-/monaco-editor-0.52.0.tgz")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "sandbox-v2-fetch-vendor"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    write_lock = "--lock" in argv
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    new_lock = dict(lock)
    ok = True
    for rel, src in FILES.items():
        dst = VENDOR / rel
        if not dst.exists():
            print(f"↓ {rel}  ({src})")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(_get(NPM + src))
        h = hashlib.sha256(dst.read_bytes()).hexdigest()
        if write_lock:
            new_lock[rel] = {"source": src, "sha256": h}
        elif rel in lock and lock[rel]["sha256"] != h:
            print(f"✗ checksum ไม่ตรง: {rel} — ลบไฟล์แล้วรันใหม่ หรือถ้าตั้งใจเปลี่ยน version ใช้ --lock")
            ok = False
        else:
            print(f"✓ {rel}")
    mdir = VENDOR / MONACO[0]
    if not (mdir / "vs" / "loader.js").exists():
        print(f"↓ monaco ({MONACO[1]}) — ~18 MB")
        raw = _get(MONACO[1])
        h = hashlib.sha256(raw).hexdigest()
        if not write_lock and "monaco.tgz" in lock and lock["monaco.tgz"]["sha256"] != h:
            print("✗ checksum ของ monaco tgz ไม่ตรง — ไม่แตกไฟล์")
            return 1
        new_lock["monaco.tgz"] = {"source": MONACO[1], "sha256": h}
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
            members = [m for m in tf.getmembers() if m.name.startswith("package/min/vs/") and ".." not in m.name]
            for m in members:
                m.name = m.name[len("package/min/"):]
            tf.extractall(mdir, members=members)
        print(f"✓ monaco → {mdir.relative_to(cfg.REPO)}")
    else:
        print("✓ monaco")
    if write_lock:
        LOCK.write_text(json.dumps(new_lock, indent=1))
        print(f"เขียน {LOCK.relative_to(cfg.REPO)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
