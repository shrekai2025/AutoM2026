from typing import List, Dict, Any, Type, Optional
from playwright.async_api import Page
from abc import ABC, abstractmethod

class BaseSpider(ABC):
    """
    Abstract base class for all spiders
    """
    def __init__(self, url: str):
        self.url = url
        
    @abstractmethod
    async def crawl(self, page: Page) -> List[Dict[str, Any]]:
        """
        Execute the crawl logic
        Returns a list of dicts: {"type": str, "date": datetime, "value": float}
        """
        pass

# Spider Registry
_SPIDERS = {}

def register_spider(name: str):
    def decorator(cls):
        _SPIDERS[name] = cls
        return cls
    return decorator

def get_spider_class(name: str) -> Optional[Type[BaseSpider]]:
    return _SPIDERS.get(name)

# Import spiders to register them
from . import farside
