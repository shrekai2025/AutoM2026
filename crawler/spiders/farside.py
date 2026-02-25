import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, TimeoutError

from . import BaseSpider, register_spider

logger = logging.getLogger(__name__)

@register_spider("farside")
class FarsideSpider(BaseSpider):
    """
    Spider for Farside Investors ETF data
    Target: https://farside.co.uk/bitcoin-etf-flow-all-data/
    """
    
    async def crawl(self, page: Page) -> List[Dict[str, Any]]:
        results = []
        try:
            # 1. Navigate
            logger.info("Navigating to Farside...")
            # Set higher timeout for loading
            page.set_default_timeout(60000)
            
            # Go to URL
            await page.goto(self.url, wait_until="domcontentloaded")
            
            # 2. Wait for Cloudflare/Loading
            # Farside often has a "checking your browser" screen. 
            # We wait for the main table to appear.
            # Selector for the main data table
            table_selector = "table" 
            
            # Try to handle potential cookie consent or specific selectors
            try:
                await page.wait_for_selector(table_selector, timeout=30000)
            except TimeoutError:
                logger.warning("Timeout waiting for table, might be checking browser...")
                # Simple wait if selector fails, sometimes it just takes time or redirects
                await asyncio.sleep(10)
            
            # 3. Extract Data
            # This is specific to Farside's layout. 
            # We look for rows in the table where the first cell is a date.
            
            # Using evaluate to run JS for extraction is often robust
            data = await page.evaluate('''() => {
                const results = [];
                const rows = document.querySelectorAll('table tr');
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length < 2) return;
                    
                    // First cell is Date (e.g., "11 Jan 2024")
                    const dateText = cells[0].innerText.trim();
                    
                    // Look for "Total" column (usually the last or specifically named)
                    // Farside table: Date | IBIT | FBTC ... | Total
                    // Let's assume the last column is Total Flow
                    const valueText = cells[cells.length - 1].innerText.trim();
                    
                    // Simple validation
                    if (!dateText || !valueText) return;
                    
                    // Check if date looks valid (regex or simple length)
                    // Farside dates are like "2024-01-11" or "11 Jan 2024"
                    
                    // Parse Value: remove commas, currency symbols
                    let cleanValue = valueText.replace(/[$,]/g, '');
                    // Handle "(12.3)" as negative -12.3 if present
                    if (cleanValue.includes('(')) {
                        cleanValue = '-' + cleanValue.replace(/[()]/g, '');
                    }
                    
                    const value = parseFloat(cleanValue);
                    
                    if (!isNaN(value)) {
                        results.push({
                            dateStr: dateText,
                            value: value
                        });
                    }
                });
                return results;
            }''')
            
            # 4. Parse Python-side
            for item in data:
                try:
                    # Parse date - try multiple formats
                    dt = self._parse_date(item["dateStr"])
                    if dt:
                        # Determine type based on URL or config?
                        # For now, default to btc_etf_flow if url contains bitcoin
                        # Determine type based on URL
                        data_type = "btc_etf_flow"
                        if "eth" in self.url.lower():
                            data_type = "eth_etf_flow"
                        elif "sol" in self.url.lower():
                            data_type = "sol_etf_flow"
                            
                        # Farside is usually in Millions ($M)
                        # We store raw value? Or convert to actual USD?
                        # Let's align with other metrics -> store as is, handle unit in UI
                        # Or convert to absolute number: 12.3 -> 12,300,000
                        val_absolute = item["value"] * 1_000_000
                        
                        results.append({
                            "type": data_type,
                            "date": dt,
                            "value": val_absolute
                        })
                except Exception as e:
                    logger.debug(f"Skipping row {item}: {e}")
                    
        except Exception as e:
            logger.error(f"Farside crawl error: {e}")
            raise e
            
        return results

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        formats = [
            "%d %b %Y", # 11 Jan 2024
            "%Y-%m-%d", # 2024-01-11
            "%b %d, %Y" # Jan 11, 2024
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
