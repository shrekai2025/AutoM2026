
import aiohttp
import asyncio

async def test_coinglass():
    urls = [
        "https://coinglass.com/api/etf/bitcoin/flow-history",
        "https://open-api.coinglass.com/public/v2/etf/bitcoin/flow-history",
        "https://fapi.coinglass.com/api/etf/bitcoin/flow-history"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://coinglass.com/bitcoin-etfs"
    }

    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                print(f"Testing {url}...")
                async with session.get(url, headers=headers) as response:
                    print(f"Status: {response.status}")
                    if response.status == 200:
                         data = await response.json()
                         print(f"Success! Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not dict'}")
                         # Dump small sample
                         print(str(data)[:200])
            except Exception as e:
                print(f"Error {url}: {e}")

if __name__ == "__main__":
    asyncio.run(test_coinglass())
