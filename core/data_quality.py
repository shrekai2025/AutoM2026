"""
DataQualityChecker — 数据完整性校验层 (Phase 1B)

嵌入数据采集管道，在数据进入策略之前进行质量校验。

检查项:
1. K 线连续性 — 检测缺失 bar (gap > 预期间隔 x 1.5)
2. 异常值过滤 — 单根 K 线涨跌幅 > 50% 标记为可疑 (不删除)
3. 时间戳对齐 — 统一到 UTC
4. 输出 completeness 分数 (0-1)
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from core.market_context import DataQualityReport

logger = logging.getLogger(__name__)

# 各时间框架的预期间隔 (秒)
INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
}


class DataQualityChecker:
    """数据质量检查器"""
    
    def __init__(
        self,
        max_price_change_pct: float = 50.0,   # 单根 K 线最大涨跌幅%
        gap_tolerance: float = 1.5,             # 缺失判定: 间隔 > 预期 x tolerance
    ):
        self.max_price_change_pct = max_price_change_pct
        self.gap_tolerance = gap_tolerance
    
    def check_klines(
        self,
        klines: List[Dict[str, Any]],
        interval: str,
    ) -> Tuple[List[Dict[str, Any]], DataQualityReport]:
        """
        检查 K 线数据质量
        
        Args:
            klines: K 线列表, 每项含 open_time/open/high/low/close/volume
            interval: 时间框架 (如 "1h", "4h")
            
        Returns:
            (cleaned_klines, quality_report)
            cleaned_klines: 原始数据 (不删除，只在可疑 bar 上标记)
            quality_report: 质量报告
        """
        if not klines:
            return klines, DataQualityReport(
                completeness=0.0,
                warnings=["空数据"],
            )
        
        warnings = []
        missing_bars = 0
        suspicious_bars = 0
        expected_interval = INTERVAL_SECONDS.get(interval)
        
        for i in range(len(klines)):
            kline = klines[i]
            
            # === 时间戳对齐 (确保 UTC) ===
            if "open_time" in kline:
                ot = kline["open_time"]
                if isinstance(ot, (int, float)):
                    # 毫秒时间戳 -> UTC datetime
                    ts = ot / 1000 if ot > 1e12 else ot
                    kline["open_time_utc"] = datetime.fromtimestamp(ts, tz=timezone.utc)
                elif isinstance(ot, datetime):
                    if ot.tzinfo is None:
                        kline["open_time_utc"] = ot.replace(tzinfo=timezone.utc)
                    else:
                        kline["open_time_utc"] = ot.astimezone(timezone.utc)
            
            # === 异常涨跌幅检测 ===
            try:
                open_price = float(kline.get("open", 0))
                close_price = float(kline.get("close", 0))
                if open_price > 0:
                    change_pct = abs((close_price - open_price) / open_price) * 100
                    if change_pct > self.max_price_change_pct:
                        kline["_suspicious"] = True
                        suspicious_bars += 1
                        warnings.append(
                            f"Bar {i}: 涨跌幅 {change_pct:.1f}% > {self.max_price_change_pct}%"
                        )
            except (ValueError, TypeError, ZeroDivisionError):
                pass
            
            # === 连续性检查 ===
            if i > 0 and expected_interval:
                prev = klines[i - 1]
                curr_time = self._get_timestamp(kline)
                prev_time = self._get_timestamp(prev)
                
                if curr_time and prev_time:
                    gap = (curr_time - prev_time).total_seconds()
                    if gap > expected_interval * self.gap_tolerance:
                        gap_bars = int(gap / expected_interval) - 1
                        missing_bars += gap_bars
                        warnings.append(
                            f"Bar {i}: 缺失 {gap_bars} 根 K 线 "
                            f"(gap={gap:.0f}s, expected={expected_interval}s)"
                        )
        
        # 计算 completeness
        total_expected = len(klines) + missing_bars
        completeness = len(klines) / total_expected if total_expected > 0 else 1.0
        
        # 限制 warnings 数量
        if len(warnings) > 10:
            truncated = len(warnings) - 10
            warnings = warnings[:10]
            warnings.append(f"... 还有 {truncated} 条警告")
        
        report = DataQualityReport(
            completeness=round(completeness, 4),
            warnings=warnings,
            missing_bars=missing_bars,
            suspicious_bars=suspicious_bars,
            timestamp_aligned=True,
        )
        
        if warnings:
            logger.warning(
                f"DataQuality [{interval}]: completeness={report.completeness:.2%}, "
                f"missing={missing_bars}, suspicious={suspicious_bars}"
            )
        
        return klines, report
    
    def check_multi_timeframe(
        self,
        klines_by_tf: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], DataQualityReport]:
        """
        检查多时间框架数据质量，返回合并报告
        """
        all_warnings = []
        total_missing = 0
        total_suspicious = 0
        completeness_scores = []
        
        for tf, klines in klines_by_tf.items():
            cleaned, report = self.check_klines(klines, tf)
            klines_by_tf[tf] = cleaned
            
            completeness_scores.append(report.completeness)
            total_missing += report.missing_bars
            total_suspicious += report.suspicious_bars
            for w in report.warnings:
                all_warnings.append(f"[{tf}] {w}")
        
        # 综合 completeness = 各时间框架的最小值 (木桶效应)
        overall_completeness = min(completeness_scores) if completeness_scores else 0.0
        
        merged = DataQualityReport(
            completeness=round(overall_completeness, 4),
            warnings=all_warnings[:15],
            missing_bars=total_missing,
            suspicious_bars=total_suspicious,
            timestamp_aligned=True,
        )
        
        return klines_by_tf, merged
    
    def _get_timestamp(self, kline: Dict[str, Any]) -> Optional[datetime]:
        """从 K 线数据中提取 UTC 时间戳"""
        # 优先使用已转换的 UTC 时间
        if "open_time_utc" in kline:
            return kline["open_time_utc"]
        
        ot = kline.get("open_time")
        if ot is None:
            return None
        
        if isinstance(ot, datetime):
            return ot
        
        if isinstance(ot, (int, float)):
            ts = ot / 1000 if ot > 1e12 else ot
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        
        return None


# 全局实例
data_quality_checker = DataQualityChecker()
