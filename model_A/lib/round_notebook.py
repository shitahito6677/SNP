"""สร้าง notebook สรุปผลรายรอบ (อ่าน results.csv + กราฟ + RESULTS.md) แล้วรันด้วย nbconvert — ใช้ซ้ำทุก round"""
import subprocess

import nbformat as nbf

from lib.paths import MODEL_A


def build(round_: str, slug: str, title: str, intro: str) -> str:
    nb = nbf.v4.new_notebook()
    C = [nbf.v4.new_markdown_cell(f"# {title}\n\n{intro}")]
    C.append(nbf.v4.new_code_cell(f'''import sys, pathlib; sys.path.insert(0, str(pathlib.Path.cwd().parent))
import pandas as pd
from IPython.display import Image, Markdown, display
from lib import report
report.banner()
r = pd.read_csv("../rounds/round_{round_}/results.csv")
cols = [c for c in ["trial_id","dec_sharpe","dec_sharpe_ew","dec_sharpe_spy","dec_cagr","dec_cagr_ew","dec_maxdd","dec_maxdd_ew",
        "S1_10","S1_25","S2_share","DSR","S6_avg_n","S6_min_n","info_sharpe","info_sharpe_ew"] if c in r.columns]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
display(r[cols].round(3))
ok = lambda c: r[c].astype(str).str.lower().eq("true")
print("ผู้เข้ารอบ (S1+S2+S3+S6):", list(r[ok("S1") & ok("S2") & ok("S3") & ok("S6")].trial_id))'''))
    C.append(nbf.v4.new_code_cell(f'''for f in sorted(pathlib.Path("../figures").glob("round_{round_}_*.png")): display(Image(filename=str(f)))'''))
    C.append(nbf.v4.new_code_cell(f'''display(Markdown(pathlib.Path("../rounds/round_{round_}/RESULTS.md").read_text()))'''))
    nb["cells"] = C
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    path = MODEL_A / "notebooks" / f"r{round_}_{slug}.ipynb"
    nbf.write(nb, path)
    subprocess.run(["python3", "-W", "ignore", "-m", "nbconvert", "--to", "notebook", "--execute", "--inplace", str(path)],
                   check=True, capture_output=True)
    subprocess.run(["python3", "-W", "ignore", "-m", "nbconvert", "--to", "html", "--output-dir", str(MODEL_A / "reports"), str(path)],
                   check=True, capture_output=True)
    return str(path)
