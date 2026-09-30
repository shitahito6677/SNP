# Round 008 — EXPLORE2 T1: ตัวกรองแนวโน้มระดับตลาด (เขียนก่อนรัน)
สเปกและเกณฑ์: `PREREG_OVERLAY.md` (ล็อกพร้อมไฟล์นี้)
- ที่มา: Faber (2007) "A Quantitative Approach to Tactical Asset Allocation"; Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum"
- ทิศทางที่คาด: ลด max drawdown ในตลาดที่มีขาลงยาว (2000–02, 2008, ญี่ปุ่นหลัง 1990) แต่เสีย CAGR ในตลาดขาขึ้นยาว/crash สั้น
- ต่างจาก round 005: เพิ่มกฎ B (TSMOM), เพิ่มตลาดเป็น 11 (รวม ^DJI, ^IXIC, EEM, SET proxy), ใช้ดอกเบี้ยเงินสดจริง (^IRX) แทน rf = 0,
  และซ้อนบนพอร์ต low accruals อันดับบนสุด
- trial ใหม่ 3 (สะสม 118); grid S4 (เฉพาะผู้เข้ารอบ): SMA ∈ {8, 10, 12} เดือน, lookback TSMOM ∈ {9, 12, 15} เดือน
