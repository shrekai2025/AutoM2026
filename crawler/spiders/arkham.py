"""
Arkham Intelligence ETF 实体页面爬虫

目标页面:
  https://intel.arkm.com/explorer/entity/blackrock  → 贝莱德 (IBIT)
  https://intel.arkm.com/explorer/entity/fidelity   → 富达 (FBTC)

数据结构 (来自截图验证):
  - Portfolio 表格: Asset | Price | Holdings | Value
  - 不需要登录，数据渲染在 DOM 中

返回格式 (与现有系统对齐):
  [
    {"type": "etf_holdings", "date": datetime, "value": float,
     "meta": {"entity": "blackrock", "asset": "BTC", "holdings": 755000, "usd_value": 49.68e9}},
    ...
  ]

反爬策略:
  - 随机延迟 + 真实 UA
  - 等待 React 渲染完成（等待具体 selector）
  - 页面滚动加速渲染
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from . import BaseSpider, register_spider

logger = logging.getLogger(__name__)


@register_spider("arkham")
class ArkhamSpider(BaseSpider):
    """
    Arkham Intelligence 实体页面爬虫
    
    URL 格式: https://intel.arkm.com/explorer/entity/{entity_slug}
    entity_slug: blackrock | fidelity | grayscale 等
    """


    async def crawl(self, page: Page) -> List[Dict[str, Any]]:
        results = []
        entity = self._parse_entity_from_url()

        try:
            logger.info(f"Arkham: navigating to {self.url} (entity={entity})")

            # ── 1. 导航 ──────────────────────────────────────
            await page.goto(
                self.url,
                wait_until="domcontentloaded",
                timeout=120000,  # BlackRock 有 6.4k 地址，需要更长超时
            )

            # ── 2. 等待 React 渲染 ────────────────────────────
            # Arkham 页面需要 JS 加载，等待 Portfolio 数据出现
            await self._wait_for_content(page)

            # ── 3. 确保数据稳定 ───────────────────────────────
            # wait_for_function 已检测到数据出现，再等 6s 确保完整渲染
            await asyncio.sleep(6)

            # ── 4. 提取 Portfolio 表格数据 ────────────────────
            holdings = await self._extract_portfolio(page, entity)
            results.extend(holdings)

            # ── 5. 提取总净值 ─────────────────────────────────
            net_value = await self._extract_net_value(page, entity)
            if net_value:
                results.append(net_value)

            logger.info(f"Arkham crawl done for {entity}: {len(results)} items")

        except PlaywrightTimeout:
            logger.warning(f"Arkham: timeout for {self.url}")
        except Exception as e:
            logger.error(f"Arkham crawl error for {entity}: {e}", exc_info=True)

        return results

    async def _wait_for_content(self, page: Page):
        """
        等待页面持仓量数据加载完成
        
        策略: 用 wait_for_function 轮询页面文本，
        等到出现 'K BTC' 或 'M ETH' （持仓量已渲染）再继续。
        这比等 networkidle 更可靠，不会因大体量页面超时。
        """
        try:
            await page.wait_for_function(
                """
                () => {
                    const text = document.body.innerText || '';
                    // 持仓量字段格式: '11.793K BTC', '755.316K BTC', '3.132M ETH'
                    return /\\d+\\.\\d+[KM]\\s+BTC/.test(text) ||
                           /\\d+\\.\\d+[KM]\\s+ETH/.test(text);
                }
                """,
                timeout=90000,  # 最多等 90 秒让 React 渲染
            )
            logger.info("Arkham: portfolio data loaded (found K BTC / M ETH)")
        except PlaywrightTimeout:
            logger.warning("Arkham: portfolio data not found in 90s, proceeding anyway")
        except Exception as e:
            logger.warning(f"Arkham wait_for_function error: {e}, proceeding anyway")
        
        # 多等 2 秒确保完全渲染
        await asyncio.sleep(2)

    async def _extract_portfolio(self, page: Page, entity: str) -> List[Dict]:
        """
        提取 Portfolio 表格: Asset | Price | Holdings | Value
        
        已验证的页面文本格式:
          "BTC\nTRADE NOW\n$65,845\n+4.01%\n11.793K BTC\n$776.52M\n+4.01%"
          "ETH\nTRADE NOW\n$1,939.86\n+6.14%\n80.114K ETH\n$155.41M\n+6.14%"
        """
        try:
            # 直接取全页文本，用 Python 正则解析
            page_text = await page.evaluate("() => document.body.innerText")
            logger.debug(f"Arkham page text snippet: {page_text[:500]}")
            holdings = self._parse_holdings_from_text(page_text, entity)
            return holdings
        except Exception as e:
            logger.error(f"Portfolio extraction failed for {entity}: {e}")
            return []

    def _parse_holdings_from_text(self, text: str, entity: str) -> List[Dict]:
        """
        从页面全文用正则解析持仓数据
        
        已验证的 Arkham 页面文本格式:
          "11.793K BTC"  → 11,793 BTC
          "80.114K ETH"  → 80,114 ETH
          "755.036K BTC" → 755,036 BTC  (BlackRock)
          "3.13M ETH"    → 3,130,000 ETH (BlackRock)
        """
        results = []
        now = datetime.utcnow()

        # 已验证格式: XX.XXXK BTC / XX.XXXM ETH
        # \d+\.\d+ = 小数形式， [KMB] = 圀位符
        # 'K' = *1000, 'M' = *1,000,000
        patterns = [
            # 小数+K: 11.793K BTC, 755.036K BTC
            (r'(\d+\.\d+)K\s+BTC', 'BTC', 1_000),
            # 整数+K: 11793K BTC
            (r'(\d{2,})K\s+BTC', 'BTC', 1_000),
            # 小数+M: 3.13M BTC
            (r'(\d+\.\d+)M\s+BTC', 'BTC', 1_000_000),
            # 小数+K ETH: 80.114K ETH
            (r'(\d+\.\d+)K\s+ETH', 'ETH', 1_000),
            # 小数+M ETH: 3.13M ETH
            (r'(\d+\.\d+)M\s+ETH', 'ETH', 1_000_000),
            # 整数+K ETH
            (r'(\d{2,})K\s+ETH', 'ETH', 1_000),
        ]

        seen_assets = set()

        for pattern, asset, multiplier in patterns:
            if asset in seen_assets:
                continue
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    amount = float(match.replace(',', '')) * multiplier

                    # 过滤明显错误值（价格而非持仓量）
                    if asset == 'BTC' and amount < 500:
                        continue  # IBIT 至少 5000+ BTC
                    if asset == 'ETH' and amount < 5000:
                        continue  # ETHA 至少 50000+ ETH

                    seen_assets.add(asset)

                    # 计算 data_type
                    if entity == "blackrock":
                        data_type = f"ibit_holdings_{asset.lower()}"
                    elif entity == "fidelity":
                        data_type = f"fbtc_holdings_{asset.lower()}"
                    else:
                        data_type = f"{entity}_holdings_{asset.lower()}"

                    results.append({
                        "type": data_type,
                        "date": now,
                        "value": amount,
                        "meta": {"entity": entity, "asset": asset, "holdings_count": amount},
                    })
                    logger.info(f"Arkham parsed: {entity} holds {amount:,.0f} {asset}")
                    break  # 每类资产只取第一个匹配

                except (ValueError, TypeError) as e:
                    logger.debug(f"Parse error for {match}: {e}")

        return results

    async def _extract_net_value(self, page: Page, entity: str) -> Optional[Dict]:
        """
        提取实体总净值（页面顶部大数字）
        
        已验证格式: "$931,930,310.57" 或 "$55.75B"
        """
        try:
            text = await page.evaluate("() => document.body.innerText.substring(0, 800)")

            # 匹配 $XXX,XXX,XXX.XX (实际页面的具体数字)
            # 或 $XX.XXB
            patterns_net = [
                (r'\$([\d,]+\.\d{2})\b', 1.0),     # $931,930,310.57
                (r'\$(\d+\.?\d*)B\b', 1e9),          # $55.75B
                (r'\$(\d+\.?\d*)M\b', 1e6),          # $930.92M
            ]

            for pattern, scale in patterns_net:
                match = re.search(pattern, text)
                if match:
                    num_str = match.group(1).replace(',', '')
                    value = float(num_str) * scale
                    # 出除明显错误（少于 $1M 说明匹配了价格）
                    if value < 1_000_000:
                        continue
                    data_type = f"{entity}_total_usd"
                    logger.info(f"Arkham {entity} total: ${value/1e9:.3f}B")
                    return {
                        "type": data_type,
                        "date": datetime.utcnow(),
                        "value": value,
                        "meta": {"entity": entity, "net_value_usd": value},
                    }

        except Exception as e:
            logger.debug(f"Net value extraction failed for {entity}: {e}")

        return None

    def _parse_entity_from_url(self) -> str:
        """从 URL 解析 entity slug"""
        # https://intel.arkm.com/explorer/entity/blackrock → blackrock
        parts = self.url.rstrip('/').split('/')
        return parts[-1] if parts else "unknown"
