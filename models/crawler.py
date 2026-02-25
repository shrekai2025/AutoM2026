from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import Base

class CrawlSource(Base):
    """
    Target website/source for crawling
    """
    __tablename__ = "crawl_sources"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # e.g., "Farside BTC"
    url = Column(String)  # Target URL
    spider_type = Column(String)  # e.g., "farside"
    schedule_interval = Column(Integer, default=360)  # Minutes, default 6 hours
    last_run_at = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)  # 1=Active, 0=Paused
    
    tasks = relationship("CrawlTask", back_populates="source")
    data = relationship("CrawledData", back_populates="source")

class CrawlTask(Base):
    """
    Execution record of a crawler run
    """
    __tablename__ = "crawl_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("crawl_sources.id"))
    status = Column(String)  # pending, running, completed, failed
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    error_log = Column(Text, nullable=True)
    items_count = Column(Integer, default=0)
    
    source = relationship("CrawlSource", back_populates="tasks")

class CrawledData(Base):
    """
    Unified storage for crawled metrics
    """
    __tablename__ = "crawled_data"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("crawl_sources.id"))
    task_id = Column(Integer, ForeignKey("crawl_tasks.id"), nullable=True)
    
    data_type = Column(String, index=True)  # e.g., "btc_etf_flow"
    date = Column(DateTime, index=True)  # The date this data point represents
    value = Column(Float)  # The numeric value (e.g., flow in millions)
    raw_content = Column(Text, nullable=True)  # Optional JSON or raw text
    created_at = Column(DateTime, default=datetime.utcnow)
    
    source = relationship("CrawlSource", back_populates="data")
