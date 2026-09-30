NAME = "ถือ SPY 100% (sanity check)"
DESCRIPTION = "ซื้อ SPY ครั้งเดียวแล้วถือตลอด — ผลต้องเท่ากับ SPY buy & hold หักค่าธรรมเนียมขาซื้อ ใช้ตรวจว่า simulator ถูก"


def decide(ctx):
    return {"SPY": 1.0}
