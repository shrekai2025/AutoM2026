"""
回测报告生成器 (Phase 2A)

生成 JSON 格式的完整回测报告，供前端渲染。
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional

from backtest.engine import BacktestResult
from backtest.metrics import calculate_metrics, BacktestMetrics
from backtest.walk_forward import WalkForwardResult


def generate_report(
    backtest_result: BacktestResult,
    walk_forward_result: Optional[WalkForwardResult] = None,
    interval: str = "1h",
) -> Dict[str, Any]:
    """
    生成完整回测报告

    Args:
        backtest_result: BacktestEngine.run() 返回值
        walk_forward_result: WalkForwardValidator.validate() 返回值 (可选)
        interval: K线时间框架

    Returns:
        JSON-serializable dict
    """
    # 计算绩效指标
    metrics = calculate_metrics(
        equity_curve=backtest_result.equity_curve,
        trades=backtest_result.trades,
        initial_capital=backtest_result.initial_capital,
        interval=interval,
    )

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "version": "2.0",

        # 配置
        "config": {
            "symbol": backtest_result.symbol,
            "interval": backtest_result.interval,
            "start_date": backtest_result.start_date,
            "end_date": backtest_result.end_date,
            "initial_capital": backtest_result.initial_capital,
            "fee_rate": backtest_result.fee_rate,
            "slippage_rate": backtest_result.slippage_rate,
        },

        # 核心指标
        "metrics": metrics.to_dict(),

        # 净值曲线 (前端 Chart.js 直接消费)
        "equity_curve": _downsample(backtest_result.equity_curve, max_points=500),

        # 交易列表
        "trades": [
            {
                "time": t.timestamp.isoformat() if isinstance(t.timestamp, datetime) else str(t.timestamp),
                "side": t.side,
                "price": round(t.price, 2),
                "amount": round(t.amount, 8),
                "value": round(t.value, 2),
                "fee": round(t.fee, 2),
                "reason": t.reason[:100],
                "conviction": round(t.conviction, 1),
            }
            for t in backtest_result.trades
        ],

        # 月度收益热力图
        "monthly_returns": metrics.monthly_returns,

        # Walk-Forward (可选)
        "walk_forward": walk_forward_result.to_dict() if walk_forward_result else None,

        # 摘要 (一句话总结)
        "summary": _generate_summary(metrics, walk_forward_result),
    }

    return report


def _generate_summary(
    metrics: BacktestMetrics,
    wf: Optional[WalkForwardResult] = None,
) -> str:
    """生成一句话摘要"""
    parts = []

    # 收益
    ret = metrics.total_return_pct
    if ret > 0:
        parts.append(f"总收益 +{ret:.1f}%")
    else:
        parts.append(f"总收益 {ret:.1f}%")

    # Sharpe
    sr = metrics.sharpe_ratio
    if sr > 2:
        parts.append(f"Sharpe {sr:.2f} (优秀)")
    elif sr > 1:
        parts.append(f"Sharpe {sr:.2f} (良好)")
    elif sr > 0:
        parts.append(f"Sharpe {sr:.2f} (一般)")
    else:
        parts.append(f"Sharpe {sr:.2f} (差)")

    # MaxDD
    dd = metrics.max_drawdown_pct
    parts.append(f"最大回撤 -{dd:.1f}%")

    # 交易
    parts.append(f"{metrics.total_trades} 笔交易")

    # Win Rate
    if metrics.win_rate > 0:
        parts.append(f"胜率 {metrics.win_rate:.0f}%")

    # Walk-Forward
    if wf:
        if wf.passed_threshold:
            parts.append("Walk-Forward 通过")
        else:
            parts.append("Walk-Forward 未通过")

    return " | ".join(parts)


def _downsample(data: list, max_points: int = 500) -> list:
    """
    降采样: 如果数据点太多, 每隔 N 个取一个
    保留首尾点
    """
    if len(data) <= max_points:
        return data

    step = len(data) / max_points
    indices = set()
    indices.add(0)
    indices.add(len(data) - 1)

    current = 0.0
    while current < len(data):
        indices.add(int(current))
        current += step

    return [data[i] for i in sorted(indices)]


def report_to_json(report: Dict[str, Any], indent: int = 2) -> str:
    """序列化报告为 JSON 字符串"""
    return json.dumps(report, ensure_ascii=False, indent=indent, default=str)
