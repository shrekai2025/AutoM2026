import aiohttp
import asyncio
import re
import json

async def test_f2pool():
    url = "https://www.f2pool.com/miners"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
                # print snippet
                print("HTML snippet length:", len(text))
                
                # Check for next.js data
                match = re.search(r'id="__NEXT_DATA__".*?>({.*?})</script>', text)
                if match:
                    data = json.loads(match.group(1))
                    print("Found NEXT_DATA")
                    with open("f2pool_data.json", "w") as f:
                        f.write(json.dumps(data, indent=2))
        except Exception as e:
            print("Error:", e)
            
asyncio.run(test_f2pool())
