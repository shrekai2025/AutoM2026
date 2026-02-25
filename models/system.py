from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from .base import Base

class ApiStatus(Base):
    """
    Tracks the health status of external APIs/Services.
    """
    __tablename__ = "api_status"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # e.g., "Binance API"
    type = Column(String)  # REST, Crawler, etc.
    status = Column(String)  # active, online, error
    last_check = Column(DateTime, default=datetime.utcnow)
    latency_ms = Column(Integer, default=0)
    message = Column(Text, nullable=True)  # Last success/error message
    
    # Optional: Track stats
    success_count_24h = Column(Integer, default=0)
    error_count_24h = Column(Integer, default=0)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
