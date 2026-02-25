import asyncio
import aiohttp

async def test_mvrv():
    async with aiohttp.ClientSession() as session:
        url = "https://fapi.coinglass.com/api/indicator/mvrv"
        try:
            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                print("Coinglass:", resp.status)
        except Exception as e:
            print("Err:", e)

    async with aiohttp.ClientSession() as session:
        url = "https://api.cryptoquant.com/v1/btc/network-indicator/mvrv"
        try:
            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                print("CryptoQuant:", resp.status)
        except Exception as e:
            print("Err:", e)

asyncio.run(test_mvrv())
