"""
回测绩效指标计算 (Phase 2A)

支持的指标:
- 总收益率、年化收益率
- Sharpe Ratio (Rf=4%)、Sortino Ratio、Calmar Ratio
- 最大回撤、最大回撤持续天数
- 胜率、盈亏比、平均持仓天数
- 月度收益热力图数据
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict


@dataclass
class BacktestMetrics:
    """回测绩效指标"""
    # 收益
    total_return_pct: float = 0          # 总收益率 %
    annual_return_pct: float = 0         # 年化收益率 %
    final_equity: float = 0
    initial_capital: float = 0

    # 风险调整收益
    sharpe_ratio: float = 0              # Sharpe (Rf=4%)
    sortino_ratio: float = 0             # Sortino
    calmar_ratio: float = 0              # Calmar (年化收益/最大回撤)

    # 回撤
    max_drawdown_pct: float = 0          # 最大回撤 %
    max_drawdown_duration_days: int = 0  # 最大回撤持续天数
    avg_drawdown_pct: float = 0          # 平均回撤 %

    # 交易统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0                  # 胜率 %
    profit_loss_ratio: float = 0         # 盈亏比 (avg win / avg loss)
    avg_trade_return_pct: float = 0      # 平均每笔收益率 %
    avg_holding_bars: int = 0            # 平均持仓 bar 数

    # 费用
    total_fees: float = 0
    total_slippage_cost: float = 0       # 估算滑点成本

    # 月度收益 (热力图用)
    monthly_returns: Dict[str, float] = field(default_factory=dict)

    # 时间
    backtest_days: int = 0
    total_bars: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "total_return_pct": round(self.total_return_pct, 2),
            "annual_return_pct": round(self.annual_return_pct, 2),
            "final_equity": round(self.final_equity, 2),
            "initial_capital": round(self.initial_capital, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "profit_loss_ratio": round(self.profit_loss_ratio, 2),
            "avg_trade_return_pct": round(self.avg_trade_return_pct, 2),
            "total_fees": round(self.total_fees, 2),
            "monthly_returns": self.monthly_returns,
            "backtest_days": self.backtest_days,
            "total_bars": self.total_bars,
        }


def calculate_metrics(
    equity_curve: List[Dict[str, Any]],
    trades: List[Any],
    initial_capital: float = 10000,
    risk_free_rate: float = 0.04,
    bars_per_year: Optional[int] = None,
    interval: str = "1h",
) -> BacktestMetrics:
    """
    从回测结果计算全部绩效指标

    Args:
        equity_curve: [{"time": ..., "equity": ..., "price": ...}, ...]
        trades: BacktestTrade 列表
        initial_capital: 初始资金
        risk_free_rate: 无风险利率 (年化, 默认 4%)
        bars_per_year: 每年 bar 数 (自动推断)
        interval: K 线间隔 (用于推断 bars_per_year)

    Returns:
        BacktestMetrics
    """
    if not equity_curve:
        return BacktestMetrics(initial_capital=initial_capital)

    # === 推断年化参数 ===
    if bars_per_year is None:
        bars_per_year = _infer_bars_per_year(interval)

    equities = [e["equity"] for e in equity_curve]
    final_equity = equities[-1]
    total_bars = len(equities)

    # === 收益率 ===
    total_return = (final_equity / initial_capital - 1) if initial_capital > 0 else 0
    years = total_bars / bars_per_year if bars_per_year > 0 else 1
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    # === 日收益率序列 (用于 Sharpe/Sortino) ===
    returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            returns.append(equities[i] / equities[i - 1] - 1)
        else:
            returns.append(0)

    # === Sharpe Ratio ===
    rf_per_bar = (1 + risk_free_rate) ** (1 / bars_per_year) - 1
    excess_returns = [r - rf_per_bar for r in returns]
    sharpe = _sharpe(excess_returns, bars_per_year)

    # === Sortino Ratio ===
    sortino = _sortino(excess_returns, bars_per_year)

    # === 最大回撤 ===
    max_dd, max_dd_duration = _max_drawdown(equities, equity_curve)

    # === Calmar Ratio ===
    calmar = annual_return / abs(max_dd / 100) if max_dd != 0 else 0

    # === 平均回撤 ===
    avg_dd = _avg_drawdown(equities)

    # === 交易统计 ===
    trade_stats = _trade_statistics(trades)

    # === 月度收益 ===
    monthly = _monthly_returns(equity_curve, initial_capital)

    # === 费用统计 ===
    total_fees = sum(getattr(t, "fee", 0) for t in trades)

    # === 时间跨度 ===
    try:
        first_time = _parse_time(equity_curve[0].get("time"))
        last_time = _parse_time(equity_curve[-1].get("time"))
        if first_time and last_time:
            backtest_days = (last_time - first_time).days
        else:
            backtest_days = int(total_bars / (bars_per_year / 365))
    except Exception:
        backtest_days = int(total_bars / (bars_per_year / 365))

    return BacktestMetrics(
        total_return_pct=total_return * 100,
        annual_return_pct=annual_return * 100,
        final_equity=final_equity,
        initial_capital=initial_capital,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown_pct=max_dd,
        max_drawdown_duration_days=max_dd_duration,
        avg_drawdown_pct=avg_dd,
        total_trades=trade_stats["total"],
        winning_trades=trade_stats["wins"],
        losing_trades=trade_stats["losses"],
        win_rate=trade_stats["win_rate"],
        profit_loss_ratio=trade_stats["pl_ratio"],
        avg_trade_return_pct=trade_stats["avg_return"],
        avg_holding_bars=trade_stats["avg_holding"],
        total_fees=total_fees,
        monthly_returns=monthly,
        backtest_days=backtest_days,
        total_bars=total_bars,
    )


# ========== 内部计算函数 ==========

def _infer_bars_per_year(interval: str) -> int:
    """推断每年 bar 数"""
    mapping = {
        "1m": 525600,
        "5m": 105120,
        "15m": 35040,
        "30m": 17520,
        "1h": 8760,
        "2h": 4380,
        "4h": 2190,
        "6h": 1460,
        "8h": 1095,
        "12h": 730,
        "1d": 365,
        "3d": 122,
        "1w": 52,
    }
    return mapping.get(interval, 8760)


def _sharpe(excess_returns: List[float], bars_per_year: int) -> float:
    """年化 Sharpe Ratio"""
    if not excess_returns or len(excess_returns) < 2:
        return 0
    mean = sum(excess_returns) / len(excess_returns)
    std = (sum((r - mean) ** 2 for r in excess_returns) / (len(excess_returns) - 1)) ** 0.5
    if std == 0:
        return 0
    return (mean / std) * math.sqrt(bars_per_year)


def _sortino(excess_returns: List[float], bars_per_year: int) -> float:
    """年化 Sortino Ratio (只考虑下行波动)"""
    if not excess_returns or len(excess_returns) < 2:
        return 0
    mean = sum(excess_returns) / len(excess_returns)
    downside = [r for r in excess_returns if r < 0]
    if not downside:
        return 10.0  # 无下行 -> 极好
    downside_std = (sum(r ** 2 for r in downside) / len(downside)) ** 0.5
    if downside_std == 0:
        return 0
    return (mean / downside_std) * math.sqrt(bars_per_year)


def _max_drawdown(equities: List[float], equity_curve: List[Dict]) -> tuple:
    """
    最大回撤及持续天数

    Returns:
        (max_drawdown_pct, max_duration_days)
    """
    if not equities:
        return 0, 0

    peak = equities[0]
    max_dd = 0
    dd_start_idx = 0
    max_dd_start = 0
    max_dd_end = 0

    for i, eq in enumerate(equities):
        if eq > peak:
            peak = eq
            dd_start_idx = i
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_start = dd_start_idx
            max_dd_end = i

    # 计算持续天数
    duration_days = 0
    try:
        start_time = _parse_time(equity_curve[max_dd_start].get("time"))
        end_time = _parse_time(equity_curve[max_dd_end].get("time"))
        if start_time and end_time:
            duration_days = (end_time - start_time).days
    except Exception:
        pass

    return max_dd, duration_days


def _avg_drawdown(equities: List[float]) -> float:
    """平均回撤"""
    if not equities:
        return 0
    peak = equities[0]
    drawdowns = []
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        if dd > 0:
            drawdowns.append(dd)
    return sum(drawdowns) / len(drawdowns) if drawdowns else 0


def _trade_statistics(trades: List[Any]) -> Dict[str, Any]:
    """交易统计"""
    if not trades:
        return {
            "total": 0, "wins": 0, "losses": 0,
            "win_rate": 0, "pl_ratio": 0,
            "avg_return": 0, "avg_holding": 0,
        }

    # 配对交易: 买入 -> 卖出
    buy_trades = [t for t in trades if t.side == "buy"]
    sell_trades = [t for t in trades if t.side == "sell"]

    paired_returns = []
    holdings = []

    for i, sell in enumerate(sell_trades):
        # 找到之前最近的买入
        matching_buys = [b for b in buy_trades if b.bar_index < sell.bar_index]
        if matching_buys:
            buy = matching_buys[-1]
            ret = (sell.price - buy.price) / buy.price if buy.price > 0 else 0
            paired_returns.append(ret)
            holdings.append(sell.bar_index - buy.bar_index)

    wins = [r for r in paired_returns if r > 0]
    losses = [r for r in paired_returns if r <= 0]

    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    pl_ratio = avg_win / avg_loss if avg_loss > 0 else (10.0 if avg_win > 0 else 0)

    return {
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(paired_returns) * 100 if paired_returns else 0,
        "pl_ratio": pl_ratio,
        "avg_return": sum(paired_returns) / len(paired_returns) * 100 if paired_returns else 0,
        "avg_holding": int(sum(holdings) / len(holdings)) if holdings else 0,
    }


def _monthly_returns(
    equity_curve: List[Dict[str, Any]],
    initial_capital: float,
) -> Dict[str, float]:
    """
    月度收益率 (热力图用)

    Returns:
        {"2024-01": 3.5, "2024-02": -1.2, ...}
    """
    if not equity_curve:
        return {}

    monthly = {}
    month_start_equity = initial_capital
    current_month = ""

    for point in equity_curve:
        t = _parse_time(point.get("time"))
        if not t:
            continue
        month_key = t.strftime("%Y-%m")

        if month_key != current_month:
            if current_month and month_start_equity > 0:
                # 记录上月收益
                monthly[current_month] = round(
                    (prev_equity / month_start_equity - 1) * 100, 2
                )
                month_start_equity = prev_equity
            current_month = month_key

        prev_equity = point["equity"]

    # 最后一个月
    if current_month and month_start_equity > 0:
        monthly[current_month] = round(
            (prev_equity / month_start_equity - 1) * 100, 2
        )

    return monthly


def _parse_time(val) -> Optional[datetime]:
    """解析时间"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    if isinstance(val, (int, float)):
        ts = val / 1000 if val > 1e12 else val
        return datetime.fromtimestamp(ts)
    return None
