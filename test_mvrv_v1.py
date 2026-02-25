import asyncio
import aiohttp

async def test_api():
    token = "VLnIUpKNI31fvtSHwASD1GdctVgIPA5epA0cJgKluF2yh0i6jqvbMCzEhk"
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://api.cryptoquant.com/v1/btc/network-indicator/mvrv"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(resp.status, await resp.text())

if __name__ == '__main__':
    asyncio.run(test_api())
