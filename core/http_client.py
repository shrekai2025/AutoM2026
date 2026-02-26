import aiohttp

class SharedHTTPClient:
    """全局共享的 HTTP 客户端，统一管理 session 生命周期"""
    _session: aiohttp.ClientSession = None
    
    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            cls._session = aiohttp.ClientSession(timeout=timeout)
        return cls._session
    
    @classmethod
    async def close(cls):
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None
