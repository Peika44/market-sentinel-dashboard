"""
Pre-canned scan results used when DEMO_MODE=true.

Bottom-building data reflects a realistic S&P 500 scan snapshot.
Breakout/Pullback data shows a representative Nasdaq-100 momentum scan.
Intraday data covers the top bottom-building candidates with mixed outcomes.

All prices are illustrative for demo purposes.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Bottom-building scan (15 stocks)
# ---------------------------------------------------------------------------

DEMO_BOTTOM_ROWS: list[dict] = [
    {
        "rank": 1, "ticker": "CTSH", "score": 75,
        "signals": {"bottom_position": False, "volume_surge": True, "rsi_recovery": True, "ma_cross": True, "macd_signal": True},
        "last_close": 53.86, "position_in_range": 0.39, "rsi_current": 53.6,
        "volume_ratio": 1.4, "macd_turning_up": True, "price_change_pct": 1.83,
    },
    {
        "rank": 2, "ticker": "AVY", "score": 75,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": True, "macd_signal": True},
        "last_close": 161.29, "position_in_range": 0.17, "rsi_current": 46.9,
        "volume_ratio": 0.8, "macd_turning_up": True, "price_change_pct": 0.42,
    },
    {
        "rank": 3, "ticker": "MDT", "score": 65,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": True, "macd_signal": False},
        "last_close": 84.15, "position_in_range": 0.22, "rsi_current": 44.2,
        "volume_ratio": 0.9, "macd_turning_up": False, "price_change_pct": 0.67,
    },
    {
        "rank": 4, "ticker": "AMGN", "score": 60,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": True, "macd_signal": False},
        "last_close": 336.49, "position_in_range": 0.20, "rsi_current": 48.8,
        "volume_ratio": 0.7, "macd_turning_up": False, "price_change_pct": 0.61,
    },
    {
        "rank": 5, "ticker": "CPB", "score": 60,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": False, "macd_signal": True},
        "last_close": 20.81, "position_in_range": 0.13, "rsi_current": 51.7,
        "volume_ratio": 1.1, "macd_turning_up": True, "price_change_pct": -0.24,
    },
    {
        "rank": 6, "ticker": "VRTX", "score": 55,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": False, "macd_signal": False},
        "last_close": 417.30, "position_in_range": 0.28, "rsi_current": 42.1,
        "volume_ratio": 0.6, "macd_turning_up": False, "price_change_pct": -0.38,
    },
    {
        "rank": 7, "ticker": "WBA", "score": 55,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": False, "macd_signal": True},
        "last_close": 11.24, "position_in_range": 0.09, "rsi_current": 40.8,
        "volume_ratio": 1.2, "macd_turning_up": True, "price_change_pct": 1.54,
    },
    {
        "rank": 8, "ticker": "BIIB", "score": 55,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": False, "ma_cross": True, "macd_signal": True},
        "last_close": 138.72, "position_in_range": 0.14, "rsi_current": 38.4,
        "volume_ratio": 0.8, "macd_turning_up": True, "price_change_pct": 0.29,
    },
    {
        "rank": 9, "ticker": "DVA", "score": 50,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": False, "macd_signal": False},
        "last_close": 97.65, "position_in_range": 0.18, "rsi_current": 43.5,
        "volume_ratio": 0.7, "macd_turning_up": False, "price_change_pct": -0.62,
    },
    {
        "rank": 10, "ticker": "PFE", "score": 50,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": False, "ma_cross": False, "macd_signal": True},
        "last_close": 23.41, "position_in_range": 0.08, "rsi_current": 37.9,
        "volume_ratio": 1.0, "macd_turning_up": True, "price_change_pct": 0.13,
    },
    {
        "rank": 11, "ticker": "BMY", "score": 50,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": False, "macd_signal": False},
        "last_close": 48.20, "position_in_range": 0.19, "rsi_current": 41.3,
        "volume_ratio": 0.9, "macd_turning_up": False, "price_change_pct": -0.45,
    },
    {
        "rank": 12, "ticker": "HOLX", "score": 45,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": False, "ma_cross": True, "macd_signal": False},
        "last_close": 63.44, "position_in_range": 0.23, "rsi_current": 39.7,
        "volume_ratio": 0.7, "macd_turning_up": False, "price_change_pct": 0.81,
    },
    {
        "rank": 13, "ticker": "KHC", "score": 45,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": False, "ma_cross": False, "macd_signal": True},
        "last_close": 27.18, "position_in_range": 0.06, "rsi_current": 35.8,
        "volume_ratio": 1.1, "macd_turning_up": True, "price_change_pct": 0.52,
    },
    {
        "rank": 14, "ticker": "VTRS", "score": 40,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": False, "ma_cross": True, "macd_signal": False},
        "last_close": 9.52, "position_in_range": 0.12, "rsi_current": 38.2,
        "volume_ratio": 0.8, "macd_turning_up": False, "price_change_pct": -0.21,
    },
    {
        "rank": 15, "ticker": "CVS", "score": 40,
        "signals": {"bottom_position": True, "volume_surge": False, "rsi_recovery": True, "ma_cross": False, "macd_signal": False},
        "last_close": 56.73, "position_in_range": 0.16, "rsi_current": 40.1,
        "volume_ratio": 0.9, "macd_turning_up": False, "price_change_pct": 0.35,
    },
]

# ---------------------------------------------------------------------------
# Breakout / Pullback scan (8 stocks)
# ---------------------------------------------------------------------------

DEMO_BREAKOUT_ROWS: list[dict] = [
    {
        "rank": 1, "ticker": "NVDA", "score": 93,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": True, "pullback_signal": False},
        "setup_type": "breakout",
        "last_close": 134.89, "breakout_level": 129.50, "close_strength": 0.86,
        "daily_return_pct": 4.16, "volume_ratio": 2.6, "price_change_pct": 4.16,
    },
    {
        "rank": 2, "ticker": "META", "score": 88,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": True, "pullback_signal": False},
        "setup_type": "breakout",
        "last_close": 596.42, "breakout_level": 578.00, "close_strength": 0.81,
        "daily_return_pct": 3.19, "volume_ratio": 2.1, "price_change_pct": 3.19,
    },
    {
        "rank": 3, "ticker": "MSFT", "score": 83,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": False, "pullback_signal": True},
        "setup_type": "pullback",
        "last_close": 444.78, "breakout_level": 451.20, "close_strength": 0.62,
        "daily_return_pct": -1.44, "volume_ratio": 1.1, "price_change_pct": -1.44,
    },
    {
        "rank": 4, "ticker": "GOOGL", "score": 79,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": True, "pullback_signal": False},
        "setup_type": "breakout",
        "last_close": 178.34, "breakout_level": 173.90, "close_strength": 0.78,
        "daily_return_pct": 2.55, "volume_ratio": 1.9, "price_change_pct": 2.55,
    },
    {
        "rank": 5, "ticker": "AAPL", "score": 76,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": False, "pullback_signal": True},
        "setup_type": "pullback",
        "last_close": 209.87, "breakout_level": 213.50, "close_strength": 0.55,
        "daily_return_pct": -1.82, "volume_ratio": 0.95, "price_change_pct": -1.82,
    },
    {
        "rank": 6, "ticker": "AMZN", "score": 72,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": False, "pullback_signal": True},
        "setup_type": "pullback",
        "last_close": 221.55, "breakout_level": 225.80, "close_strength": 0.47,
        "daily_return_pct": -2.11, "volume_ratio": 0.92, "price_change_pct": -2.11,
    },
    {
        "rank": 7, "ticker": "TSLA", "score": 68,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": True, "pullback_signal": False},
        "setup_type": "breakout",
        "last_close": 285.60, "breakout_level": 279.40, "close_strength": 0.73,
        "daily_return_pct": 2.64, "volume_ratio": 1.82, "price_change_pct": 2.64,
    },
    {
        "rank": 8, "ticker": "AMD", "score": 65,
        "signals": {"market_aligned": True, "trend_up": True, "volume_surge": True, "breakout_signal": False, "pullback_signal": True},
        "setup_type": "pullback",
        "last_close": 114.22, "breakout_level": 118.70, "close_strength": 0.41,
        "daily_return_pct": -2.38, "volume_ratio": 0.91, "price_change_pct": -2.38,
    },
]

# ---------------------------------------------------------------------------
# Intraday confirmation results for the top bottom-building candidates
# ---------------------------------------------------------------------------

DEMO_INTRADAY_ROWS: dict[str, dict] = {
    "CTSH": {
        "ticker": "CTSH", "confirmed": True, "signals_passed": 5,
        "signals": {"gap_ok": True, "breakout_held": True, "orderflow_ok": True, "pullback_ok": True, "spoofing_ok": True},
        "open_gap_pct": 1.24, "session_high": 54.45, "current_price": 53.86,
        "pullback_from_high_pct": 1.08, "volume_ratio": 1.82, "breakout_hold_minutes": 42,
        "entry_price": 53.10, "stop_price": 51.50, "target_price": 56.90,
        "snapshot_time": "14:32", "note": "突破保持42分钟，订单流健康，无虚假信号",
    },
    "AVY": {
        "ticker": "AVY", "confirmed": True, "signals_passed": 5,
        "signals": {"gap_ok": True, "breakout_held": True, "orderflow_ok": True, "pullback_ok": True, "spoofing_ok": True},
        "open_gap_pct": 0.83, "session_high": 163.20, "current_price": 161.29,
        "pullback_from_high_pct": 1.17, "volume_ratio": 1.41, "breakout_hold_minutes": 31,
        "entry_price": 160.50, "stop_price": 155.70, "target_price": 170.30,
        "snapshot_time": "14:11", "note": "缩量回调质量好，买方主动成交占优",
    },
    "MDT": {
        "ticker": "MDT", "confirmed": True, "signals_passed": 4,
        "signals": {"gap_ok": True, "breakout_held": True, "orderflow_ok": True, "pullback_ok": True, "spoofing_ok": False},
        "open_gap_pct": 0.57, "session_high": 84.98, "current_price": 84.15,
        "pullback_from_high_pct": 0.98, "volume_ratio": 1.23, "breakout_hold_minutes": 24,
        "entry_price": 83.80, "stop_price": 81.40, "target_price": 88.10,
        "snapshot_time": "13:58", "note": "4/5 信号通过，尾盘出现小量撤单，谨慎",
    },
    "AMGN": {
        "ticker": "AMGN", "confirmed": False, "signals_passed": 3,
        "signals": {"gap_ok": True, "breakout_held": True, "orderflow_ok": True, "pullback_ok": False, "spoofing_ok": False},
        "open_gap_pct": 0.52, "session_high": 339.80, "current_price": 336.49,
        "pullback_from_high_pct": 2.44, "volume_ratio": 0.91, "breakout_hold_minutes": 15,
        "entry_price": None, "stop_price": None, "target_price": None,
        "snapshot_time": "13:42", "note": "回调幅度偏大(2.4%)，高位撤单较多，未确认",
    },
    "CPB": {
        "ticker": "CPB", "confirmed": False, "signals_passed": 2,
        "signals": {"gap_ok": False, "breakout_held": True, "orderflow_ok": False, "pullback_ok": True, "spoofing_ok": True},
        "open_gap_pct": -0.31, "session_high": 21.05, "current_price": 20.81,
        "pullback_from_high_pct": 1.14, "volume_ratio": 0.72, "breakout_hold_minutes": 9,
        "entry_price": None, "stop_price": None, "target_price": None,
        "snapshot_time": "13:19", "note": "成交量不足，订单流信号弱，等待放量",
    },
    "VRTX": {
        "ticker": "VRTX", "confirmed": False, "signals_passed": 2,
        "signals": {"gap_ok": False, "breakout_held": False, "orderflow_ok": True, "pullback_ok": True, "spoofing_ok": False},
        "open_gap_pct": -0.48, "session_high": 419.60, "current_price": 417.30,
        "pullback_from_high_pct": 0.55, "volume_ratio": 0.61, "breakout_hold_minutes": 0,
        "entry_price": None, "stop_price": None, "target_price": None,
        "snapshot_time": "13:05", "note": "量能不足，未突破阻力位，暂观望",
    },
    "WBA": {
        "ticker": "WBA", "confirmed": False, "signals_passed": 3,
        "signals": {"gap_ok": True, "breakout_held": True, "orderflow_ok": False, "pullback_ok": True, "spoofing_ok": False},
        "open_gap_pct": 1.18, "session_high": 11.42, "current_price": 11.24,
        "pullback_from_high_pct": 1.58, "volume_ratio": 1.24, "breakout_hold_minutes": 18,
        "entry_price": None, "stop_price": None, "target_price": None,
        "snapshot_time": "14:03", "note": "低价股盘中波动大，订单流信号不稳定",
    },
    "BIIB": {
        "ticker": "BIIB", "confirmed": False, "signals_passed": 2,
        "signals": {"gap_ok": False, "breakout_held": True, "orderflow_ok": False, "pullback_ok": True, "spoofing_ok": False},
        "open_gap_pct": 0.22, "session_high": 139.88, "current_price": 138.72,
        "pullback_from_high_pct": 0.83, "volume_ratio": 0.77, "breakout_hold_minutes": 11,
        "entry_price": None, "stop_price": None, "target_price": None,
        "snapshot_time": "13:34", "note": "成交量偏低，买方力量不足以确认突破",
    },
}
