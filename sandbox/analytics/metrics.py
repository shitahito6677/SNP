"""
Strategy performance metrics — คำนวณจาก trade_log + portfolio_value_series ที่
sandbox/engine/simulate.py สร้างไว้แล้ว (ไม่ดึงข้อมูลเพิ่ม, deterministic)

⚠️ metric พวกนี้ทดสอบว่า**โค้ดคำนวณถูก**เท่านั้น signal ที่ใช้รัน simulation ส่วนใหญ่ยังมาจาก
stub (ดู sandbox/inference/) ตัวเลข return/drawdown ที่ได้จึง**ไม่ได้แปลว่ากลยุทธ์นี้จะทำ
กำไรได้จริง** (banner บนหน้า Strategies ย้ำเรื่องนี้ซ้ำอีกที)

win rate คำนวณด้วย running weighted-average cost basis ต่อ ticker (ไม่ใช่ FIFO lot) — ใช้ได้
พอดีกับ strategy_v1 เพราะ "sell" ขายทั้งหมดที่ถือทุกครั้ง (ไม่มี partial sell ให้ FIFO ยุ่งยาก)
ถ้า strategy ในอนาคตทำ partial sell ต้องทบทวน logic นี้ใหม่
"""


def compute_max_drawdown_pct(portfolio_value_series: list) -> float:
    """Max drawdown % — จุดที่มูลค่าร่วงมากสุดจาก peak ก่อนหน้า (running max) ไม่ใช่จาก
    initial cash เฉยๆ (drawdown ที่ถูกต้องต้องเทียบกับ peak ที่เคยขึ้นไปแล้ว)"""
    peak = float("-inf")
    max_dd = 0.0
    for point in portfolio_value_series:
        value = point["value"]
        peak = max(peak, value)
        if peak > 0:
            dd = (peak - value) / peak * 100
            max_dd = max(max_dd, dd)
    return round(max_dd, 2)


def compute_win_rate(trade_log: list) -> dict:
    """คืน {closed_trades, wins, win_rate_pct} — "ปิด" หมายถึง sell (strategy_v1 sell ทั้งหมด
    ที่ถือทุกครั้ง ไม่มี partial) ใช้ running weighted-average cost ต่อ ticker เทียบกับราคา
    sell เพื่อตัดสิน กำไร/ขาดทุน"""
    avg_cost = {}  # ticker -> (total_cost, total_shares)
    wins = 0
    closed_trades = 0

    for t in trade_log:
        ticker = t["ticker"]
        if t["type"] in ("buy", "dca"):
            cost = t["shares"] * t["price"]
            prev_cost, prev_shares = avg_cost.get(ticker, (0.0, 0.0))
            avg_cost[ticker] = (prev_cost + cost, prev_shares + t["shares"])
        elif t["type"] == "sell":
            prev_cost, prev_shares = avg_cost.get(ticker, (0.0, 0.0))
            closed_trades += 1
            if prev_shares > 0:
                avg_price = prev_cost / prev_shares
                if t["price"] > avg_price:
                    wins += 1
            avg_cost[ticker] = (0.0, 0.0)  # sell หมดสถานะ (strategy_v1 sell 100% เสมอ)

    win_rate_pct = round(wins / closed_trades * 100, 2) if closed_trades else None
    return {"closed_trades": closed_trades, "wins": wins, "win_rate_pct": win_rate_pct}


def compute_metrics(trade_log: list, portfolio_value_series: list, initial_cash: float) -> dict:
    final_value = portfolio_value_series[-1]["value"] if portfolio_value_series else initial_cash
    total_return_pct = round((final_value - initial_cash) / initial_cash * 100, 2) if initial_cash else None

    win_stats = compute_win_rate(trade_log)

    return {
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": compute_max_drawdown_pct(portfolio_value_series),
        "total_trades": len(trade_log),
        "closed_trades": win_stats["closed_trades"],
        "win_rate_pct": win_stats["win_rate_pct"],
        "final_value": final_value,
    }


def compute_buy_and_hold(price_by_ticker: dict, dates: list, ticker_set: list, initial_cash: float) -> dict:
    """Benchmark: ซื้อ ticker_set เท่าๆ กันที่วันแรกของช่วง แล้วถือเฉยๆตลอด (ไม่มี trade
    เลย) คำนวณ metric ชุดเดียวกับ strategy เพื่อเทียบกันตรงๆ"""
    if not dates or not ticker_set:
        return None

    first_date = dates[0]
    amount_each = initial_cash / len(ticker_set)
    shares = {}
    for ticker in ticker_set:
        price = price_by_ticker.get(ticker, {}).get(first_date)
        shares[ticker] = (amount_each / price) if price else 0.0

    series = []
    for date in dates:
        value = sum(
            shares[t] * price_by_ticker.get(t, {}).get(date, 0)
            for t in ticker_set
            if price_by_ticker.get(t, {}).get(date) is not None
        )
        series.append({"date": date, "value": round(value, 2)})

    metrics = compute_metrics([], series, initial_cash)
    return {"portfolio_value_series": series, **metrics}
