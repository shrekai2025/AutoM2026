import logging
import time
from datetime import datetime
from sqlalchemy import select
from core.database import AsyncSessionLocal
from models.system import ApiStatus

logger = logging.getLogger(__name__)

class SystemMonitor:
    """
    Helper to record and retrieve system status.
    """
    
    @staticmethod
    async def record_status(name: str, type: str, is_success: bool, latency_ms: int = 0, message: str = ""):
        """
        Record an API check result.
        """
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(select(ApiStatus).where(ApiStatus.name == name))
                status_record = result.scalar_one_or_none()
                
                if not status_record:
                    status_record = ApiStatus(name=name, type=type, success_count_24h=0, error_count_24h=0)
                    db.add(status_record)
                
                # Update status
                status_record.status = "online" if is_success else "error"
                status_record.last_check = datetime.utcnow()
                status_record.latency_ms = latency_ms
                status_record.message = message
                
                # Ensure counters are int
                if status_record.success_count_24h is None:
                    status_record.success_count_24h = 0
                if status_record.error_count_24h is None:
                    status_record.error_count_24h = 0
                
                # Update counters (simple daily reset logic could be added later, currently just cumulative)
                if is_success:
                    status_record.success_count_24h += 1
                else:
                    status_record.error_count_24h += 1
                    
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to record system status for {name}: {e}")

monitor = SystemMonitor()
