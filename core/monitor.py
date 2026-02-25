"""
系统监控（纯内存版）

不写数据库，用一个内存 deque 记录最近的 API 请求日志。
/system/status 页面直接读这个内存列表。
"""
import logging
import time
from collections import deque
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List

logger = logging.getLogger(__name__)

# 最多保留最近 200 条日志
MAX_LOG_ENTRIES = 200


@dataclass
class ApiLogEntry:
    name: str           # 服务名称, e.g. "Binance API (Public)"
    type: str           # 类型, e.g. "REST", "Macro"
    status: str         # "online" or "error"
    latency_ms: int     # 延迟 (ms)
    message: str        # 描述
    timestamp: datetime  # 记录时间


class SystemMonitor:
    """
    纯内存 API 状态记录器。
    每个服务保留最新一条状态 + 全局历史日志。
    """

    def __init__(self):
        # 全局日志队列（最新在前）
        self._logs: deque[ApiLogEntry] = deque(maxlen=MAX_LOG_ENTRIES)
        # 每个服务的最新状态
        self._latest: dict[str, ApiLogEntry] = {}

    async def record_status(
        self,
        name: str,
        type: str,
        is_success: bool,
        latency_ms: int = 0,
        message: str = "",
        **kwargs,  # 忽略旧代码传入的 db 等参数
    ):
        """记录一条 API 状态（写入内存，不碰数据库）"""
        entry = ApiLogEntry(
            name=name,
            type=type,
            status="online" if is_success else "error",
            latency_ms=latency_ms,
            message=message,
            timestamp=datetime.utcnow(),
        )
        self._logs.appendleft(entry)
        self._latest[name] = entry

    def get_latest_status(self) -> List[dict]:
        """获取每个服务的最新状态（用于 /system/status 页面表格）"""
        return [
            {
                "name": e.name,
                "type": e.type,
                "status": e.status,
                "latency_ms": e.latency_ms,
                "message": e.message,
                "last_check": e.timestamp,
            }
            for e in sorted(self._latest.values(), key=lambda x: x.name)
        ]

    def get_recent_logs(self, limit: int = 50) -> List[dict]:
        """获取最近 N 条日志（用于 /system/status 页面日志区域）"""
        result = []
        for entry in list(self._logs)[:limit]:
            result.append({
                "name": entry.name,
                "type": entry.type,
                "status": entry.status,
                "latency_ms": entry.latency_ms,
                "message": entry.message,
                "timestamp": entry.timestamp,
            })
        return result


monitor = SystemMonitor()
