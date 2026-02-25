import logging
import time
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AsyncSessionLocal
from models.system import ApiStatus

logger = logging.getLogger(__name__)


class SystemMonitor:
    """
    Helper to record and retrieve system status.
    """

    @staticmethod
    async def record_status(
        name: str,
        type: str,
        is_success: bool,
        latency_ms: int = 0,
        message: str = "",
        db: Optional[AsyncSession] = None,
    ):
        """
        Record an API check result.

        If `db` is provided, uses the existing session (no extra connection opened).
        If `db` is None, opens its own short-lived session.
        This prevents "database is locked" errors when called from within an
        existing DB session context (e.g., _refresh_market_cache).
        """
        # If called from within an existing session, use a fire-and-forget
        # approach in a separate task so we don't block the caller or nest sessions.
        if db is not None:
            # Don't nest into the caller's transaction - schedule as standalone
            import asyncio
            asyncio.create_task(SystemMonitor._write_status(name, type, is_success, latency_ms, message))
            return

        await SystemMonitor._write_status(name, type, is_success, latency_ms, message)

    @staticmethod
    async def _write_status(name: str, type: str, is_success: bool, latency_ms: int, message: str):
        """Internal: open own session and write status record."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(ApiStatus).where(ApiStatus.name == name))
                status_record = result.scalar_one_or_none()

                if not status_record:
                    status_record = ApiStatus(name=name, type=type, success_count_24h=0, error_count_24h=0)
                    db.add(status_record)

                status_record.status = "online" if is_success else "error"
                status_record.last_check = datetime.utcnow()
                status_record.latency_ms = latency_ms
                status_record.message = message

                if status_record.success_count_24h is None:
                    status_record.success_count_24h = 0
                if status_record.error_count_24h is None:
                    status_record.error_count_24h = 0

                if is_success:
                    status_record.success_count_24h += 1
                else:
                    status_record.error_count_24h += 1

                await db.commit()
        except Exception as e:
            logger.error(f"Failed to record system status for '{name}': {e}", exc_info=True)


monitor = SystemMonitor()
