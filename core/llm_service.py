"""
LLM Service - OpenRouter Client for AutoM2026

Provides async LLM chat completions via OpenRouter API.
"""
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import httpx

from config import (
    OPENROUTER_API_KEY, 
    OPENROUTER_BASE_URL, 
    LLM_MODEL,
    LLM_ENABLED,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM Response container"""
    content: str
    model: str
    usage: Dict[str, int]
    raw_response: Optional[Dict] = None


class LLMService:
    """
    Async LLM client using OpenRouter API.
    
    Features:
    - Async HTTP requests with httpx
    - Retry logic with exponential backoff
    - Structured response parsing
    """
    
    def __init__(
        self,
        api_key: str = OPENROUTER_API_KEY,
        base_url: str = OPENROUTER_BASE_URL,
        default_model: str = LLM_MODEL,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.enabled = LLM_ENABLED and bool(api_key)
        
        if not self.enabled:
            logger.warning("LLM Service disabled (no API key or LLM_ENABLED=false)")
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        retries: int = 3,
        retry_delay: float = 1.0,
    ) -> LLMResponse:
        """
        Send chat completion request to OpenRouter.
        
        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
            model: Model identifier (default from config)
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens to generate
            retries: Number of retries for network errors
            retry_delay: Initial delay between retries (doubles each retry)
            
        Returns:
            LLMResponse with generated content
            
        Raises:
            RuntimeError: If LLM is disabled
            httpx.HTTPError: If API request fails after retries
        """
        if not self.enabled:
            raise RuntimeError("LLM Service is not enabled. Check API key and LLM_ENABLED config.")
        
        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://automoney.local",
            "X-Title": "AutoM2026",
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        last_exception = None
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                
                logger.info(f"LLM call success: {model}, tokens={usage.get('total_tokens', 'N/A')}")
                
                return LLMResponse(
                    content=content,
                    model=model,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    raw_response=data,
                )
                
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as e:
                last_exception = e
                if attempt < retries:
                    logger.warning(f"LLM call failed ({e}), retrying in {retry_delay}s... (Attempt {attempt+1}/{retries})")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"LLM call failed after {retries} retries: {e}")
                    raise
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"LLM API error: {e.response.status_code} - {e.response.text[:500]}")
                raise
    
    def is_enabled(self) -> bool:
        """Check if LLM service is available"""
        return self.enabled


# Global LLM service instance
llm_service = LLMService()
