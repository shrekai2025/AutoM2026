"""
Walk-Forward 防过拟合验证 (Phase 2A)

滚动窗口验证:
1. 将历史数据分为多个 训练/验证 窗口
2. 在每个验证窗口上运行策略
3. 汇总各窗口的 Sharpe/MaxDD 稳定性
4. 成本敏感性测试: 手续费/滑点 +-50% 下的绩效变化
5. 上线门槛: walk-forward 各窗口 Sharpe 中位数 > 0.8 且无窗口 MaxDD > 25%
"""
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Type

from strategies.base import BaseStrategy
from backtest.engine import BacktestEngine, BacktestResult
from backtest.metrics import calculate_metrics, BacktestMetrics

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """单个窗口的结果"""
    window_index: int
    train_start: int          # K 线索引
    train_end: int
    test_start: int
    test_end: int
    train_bars: int
    test_bars: int
    metrics: Optional[BacktestMetrics] = None
    error: Optional[str] = None


@dataclass
class WalkForwardResult:
    """Walk-Forward 验证结果"""
    # 配置
    total_klines: int = 0
    train_bars: int = 0
    test_bars: int = 0
    step_bars: int = 0
    num_windows: int = 0

    # 各窗口结果
    windows: List[WindowResult] = field(default_factory=list)

    # 汇总指标
    sharpe_median: float = 0
    sharpe_mean: float = 0
    sharpe_std: float = 0
    sharpe_min: float = 0
    max_drawdown_worst: float = 0      # 最差窗口 MaxDD
    max_drawdown_median: float = 0
    return_median: float = 0
    win_rate_median: float = 0

    # 成本敏感性
    cost_sensitivity: Dict[str, Any] = field(default_factory=dict)

    # 上线判定
    passes_threshold: bool = False
    threshold_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_klines": self.total_klines,
            "train_bars": self.train_bars,
            "test_bars": self.test_bars,
            "step_bars": self.step_bars,
            "num_windows": self.num_windows,
            "sharpe_median": round(self.sharpe_median, 3),
            "sharpe_mean": round(self.sharpe_mean, 3),
            "sharpe_std": round(self.sharpe_std, 3),
            "sharpe_min": round(self.sharpe_min, 3),
            "max_drawdown_worst": round(self.max_drawdown_worst, 2),
            "max_drawdown_median": round(self.max_drawdown_median, 2),
            "return_median": round(self.return_median, 2),
            "passes_threshold": self.passes_threshold,
            "threshold_details": self.threshold_details,
            "cost_sensitivity": self.cost_sensitivity,
            "windows": [
                {
                    "index": w.window_index,
                    "test_bars": w.test_bars,
                    "sharpe": round(w.metrics.sharpe_ratio, 3) if w.metrics else None,
                    "max_dd": round(w.metrics.max_drawdown_pct, 2) if w.metrics else None,
                    "return_pct": round(w.metrics.total_return_pct, 2) if w.metrics else None,
                    "trades": w.metrics.total_trades if w.metrics else 0,
                    "error": w.error,
                }
                for w in self.windows
            ],
        }


class WalkForwardValidator:
    """
    Walk-Forward 验证器

    用法:
        validator = WalkForwardValidator()
        result = await validator.validate(
            strategy_class=TAStrategy,
            strategy_config={...},
            klines=all_klines,
            interval="1h",
        )
        if result.passes_threshold:
            print("策略通过验证，可以上线")
    """

    def __init__(
        self,
        train_bars: int = 4320,       # 训练窗口 (默认 6 个月 x 720h)
        test_bars: int = 1440,        # 验证窗口 (默认 2 个月 x 720h)
        step_bars: int = 1440,        # 滑动步长 (默认 2 个月)
        initial_capital: float = 10000,
        fee_rate: float = 0.001,
        slippage_rate: float = 0.0005,
        # 上线门槛
        min_sharpe_median: float = 0.8,
        max_dd_threshold: float = 25.0,  # 任何窗口 MaxDD > 25% 则不通过
    ):
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.step_bars = step_bars
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.min_sharpe_median = min_sharpe_median
        self.max_dd_threshold = max_dd_threshold

    async def validate(
        self,
        strategy_class: Type[BaseStrategy],
        strategy_config: Optional[Dict[str, Any]] = None,
        klines: List[Dict[str, Any]] = None,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        run_cost_sensitivity: bool = True,
        progress_callback=None,
    ) -> WalkForwardResult:
        """
        运行 Walk-Forward 验证

        Args:
            strategy_class: 策略类
            strategy_config: 策略配置
            klines: 完整历史 K 线
            symbol: 交易对
            interval: 时间框架
            run_cost_sensitivity: 是否运行成本敏感性测试
            progress_callback: 进度回调
        """
        if not klines:
            raise ValueError("No klines provided")

        total = len(klines)
        min_required = self.train_bars + self.test_bars
        if total < min_required:
            raise ValueError(
                f"Not enough data: {total} bars, need >= {min_required} "
                f"(train={self.train_bars} + test={self.test_bars})"
            )

        # === 生成窗口 ===
        windows_config = []
        start = 0
        while start + self.train_bars + self.test_bars <= total:
            train_start = start
            train_end = start + self.train_bars
            test_start = train_end
            test_end = min(train_end + self.test_bars, total)
            windows_config.append((train_start, train_end, test_start, test_end))
            start += self.step_bars

        num_windows = len(windows_config)
        if num_windows == 0:
            raise ValueError("Cannot create any walk-forward windows")

        logger.info(
            f"Walk-Forward: {num_windows} windows, "
            f"train={self.train_bars}, test={self.test_bars}, step={self.step_bars}"
        )

        # === 逐窗口回测 ===
        window_results: List[WindowResult] = []

        for idx, (tr_s, tr_e, te_s, te_e) in enumerate(windows_config):
            # 只在验证窗口上运行 (训练窗口用于预热)
            # 策略拿到 train+test 的数据，但只在 test 区间产生交易
            test_klines = klines[te_s:te_e]
            # 给策略一些预热数据 (取训练窗口最后 200 条 + test)
            warmup_start = max(tr_s, te_s - 200)
            full_klines = klines[warmup_start:te_e]

            wr = WindowResult(
                window_index=idx,
                train_start=tr_s,
                train_end=tr_e,
                test_start=te_s,
                test_end=te_e,
                train_bars=tr_e - tr_s,
                test_bars=te_e - te_s,
            )

            try:
                engine = BacktestEngine(
                    initial_capital=self.initial_capital,
                    fee_rate=self.fee_rate,
                    slippage_rate=self.slippage_rate,
                    use_risk_manager=False,  # WF 验证不用风控，测策略纯表现
                )
                bt_result = await engine.run(
                    strategy_class=strategy_class,
                    strategy_config=strategy_config,
                    klines=full_klines,
                    symbol=symbol,
                    interval=interval,
                )
                wr.metrics = calculate_metrics(
                    equity_curve=bt_result.equity_curve,
                    trades=bt_result.trades,
                    initial_capital=self.initial_capital,
                    interval=interval,
                )
            except Exception as e:
                logger.error(f"Window {idx} failed: {e}")
                wr.error = str(e)

            window_results.append(wr)

            if progress_callback:
                await progress_callback(idx + 1, num_windows)

        # === 汇总 ===
        result = WalkForwardResult(
            total_klines=total,
            train_bars=self.train_bars,
            test_bars=self.test_bars,
            step_bars=self.step_bars,
            num_windows=num_windows,
            windows=window_results,
        )

        valid_windows = [w for w in window_results if w.metrics is not None]
        if valid_windows:
            sharpes = [w.metrics.sharpe_ratio for w in valid_windows]
            max_dds = [w.metrics.max_drawdown_pct for w in valid_windows]
            returns = [w.metrics.total_return_pct for w in valid_windows]

            result.sharpe_median = statistics.median(sharpes) if sharpes else 0
            result.sharpe_mean = statistics.mean(sharpes) if sharpes else 0
            result.sharpe_std = statistics.stdev(sharpes) if len(sharpes) > 1 else 0
            result.sharpe_min = min(sharpes) if sharpes else 0
            result.max_drawdown_worst = max(max_dds) if max_dds else 0
            result.max_drawdown_median = statistics.median(max_dds) if max_dds else 0
            result.return_median = statistics.median(returns) if returns else 0

            # === 上线门槛判定 ===
            sharpe_pass = result.sharpe_median >= self.min_sharpe_median
            dd_pass = result.max_drawdown_worst <= self.max_dd_threshold

            result.passes_threshold = sharpe_pass and dd_pass
            result.threshold_details = {
                "sharpe_median": round(result.sharpe_median, 3),
                "sharpe_threshold": self.min_sharpe_median,
                "sharpe_pass": sharpe_pass,
                "max_dd_worst": round(result.max_drawdown_worst, 2),
                "max_dd_threshold": self.max_dd_threshold,
                "dd_pass": dd_pass,
                "valid_windows": len(valid_windows),
                "total_windows": num_windows,
            }

        # === 成本敏感性测试 ===
        if run_cost_sensitivity and valid_windows:
            result.cost_sensitivity = await self._cost_sensitivity_test(
                strategy_class=strategy_class,
                strategy_config=strategy_config,
                klines=klines,
                symbol=symbol,
                interval=interval,
            )

        logger.info(
            f"Walk-Forward complete: {num_windows} windows, "
            f"Sharpe median={result.sharpe_median:.3f}, "
            f"MaxDD worst={result.max_drawdown_worst:.1f}%, "
            f"Pass={'YES' if result.passes_threshold else 'NO'}"
        )

        return result

    async def _cost_sensitivity_test(
        self,
        strategy_class: Type[BaseStrategy],
        strategy_config: Optional[Dict],
        klines: List[Dict],
        symbol: str,
        interval: str,
    ) -> Dict[str, Any]:
        """
        成本敏感性测试: 在 fee/slippage +-50% 下运行回测
        """
        scenarios = {
            "base": (self.fee_rate, self.slippage_rate),
            "high_cost": (self.fee_rate * 1.5, self.slippage_rate * 1.5),
            "low_cost": (self.fee_rate * 0.5, self.slippage_rate * 0.5),
        }

        results = {}
        for name, (fee, slip) in scenarios.items():
            try:
                engine = BacktestEngine(
                    initial_capital=self.initial_capital,
                    fee_rate=fee,
                    slippage_rate=slip,
                    use_risk_manager=False,
                )
                bt = await engine.run(
                    strategy_class=strategy_class,
                    strategy_config=strategy_config,
                    klines=klines,
                    symbol=symbol,
                    interval=interval,
                )
                m = calculate_metrics(
                    bt.equity_curve, bt.trades,
                    self.initial_capital, interval=interval,
                )
                results[name] = {
                    "fee_rate": fee,
                    "slippage_rate": slip,
                    "total_return_pct": round(m.total_return_pct, 2),
                    "sharpe": round(m.sharpe_ratio, 3),
                    "max_dd": round(m.max_drawdown_pct, 2),
                }
            except Exception as e:
                results[name] = {"error": str(e)}

        # 成本敏感性 = high_cost 和 base 的 Sharpe 差值
        base_sharpe = results.get("base", {}).get("sharpe", 0)
        high_sharpe = results.get("high_cost", {}).get("sharpe", 0)
        results["sensitivity_score"] = round(base_sharpe - high_sharpe, 3)

        return results
