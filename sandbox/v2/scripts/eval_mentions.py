"""วัดความแม่นยำของ auto-detect กับ tests/mention_samples.json — python3 -m sandbox.v2.scripts.eval_mentions"""
import json

from sandbox.v2 import config as cfg, news


def main():
    s = json.loads((cfg.V2 / "tests" / "mention_samples.json").read_text())["samples"]
    tp = fp = fn = macro_ok = 0
    for i, x in enumerate(s, 1):
        d = news.detect(x["text"])
        got = {m["ticker"] for m in d["mentions"]}
        exp = set(x["expected"])
        tp += len(got & exp); fp += len(got - exp); fn += len(exp - got)
        mo = d["macro"]["suggest"] == x["macro"]
        macro_ok += mo
        print(f"{i:2d}. ถูก {sorted(got & exp)} ผิด {sorted(got - exp)} พลาด {sorted(exp - got)} · macro {'✓' if mo else '✗'} ({d['macro']['keywords']})")
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    print(f"ticker: ถูก {tp} · ผิด (false positive) {fp} · พลาด (missed) {fn} · precision {prec:.2f} · recall {rec:.2f}")
    print(f"macro suggestion ถูก {macro_ok}/{len(s)}")
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "macro_ok": macro_ok, "n": len(s)}


if __name__ == "__main__":
    main()
