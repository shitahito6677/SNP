import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# B version ที่ build จากข่าว manual (manual-labels*) เขียนลงโฟลเดอร์ชั่วคราวระหว่าง test — ไม่ทับไฟล์ที่สร้างจากข่าวจริงของผู้ใช้
# (test ที่เปิด server เป็น subprocess ใช้ config จริง = เหมือนผู้ใช้เปิด server เอง)
import tempfile  # noqa: E402

from sandbox.v2 import config as _cfg  # noqa: E402

_cfg.MODEL_EXPORT_ROOTS["B"] = Path(tempfile.mkdtemp(prefix="sbv2_model_B_export_"))
