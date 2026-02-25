"""
Arkham Intelligence 爬虫独立测试脚本

运行: python test_arkham_spider.py
需要系统已安装 Playwright Chromium (playwright install chromium)
"""
import asyncio
import sys
import os
import logging

# 加载项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from playwright.async_api import async_playwright
    from crawler.spiders.arkham import ArkhamSpider

    print("=" * 60)
    print("Arkham Intelligence ETF 爬虫测试")
    print("=" * 60)

    playwright_inst = None
    browser = None

    try:
        playwright_inst = await async_playwright().start()
        browser = await playwright_inst.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        # ── 测试1: 贝莱德 (IBIT) ─────────────────────────────
        print("\n[测试1] BlackRock / IBIT")
        print("-" * 40)
        page1 = await context.new_page()
        spider1 = ArkhamSpider("https://intel.arkm.com/explorer/entity/blackrock")
        results1 = await spider1.crawl(page1)
        await page1.close()

        if results1:
            print(f"✅ 获取 {len(results1)} 条数据:")
            for r in results1:
                print(f"   [{r['type']}] value={r['value']:,.2f}")
        else:
            print("❌ 未获取到数据")

        # ── 测试2: 富达 (FBTC) ───────────────────────────────
        print("\n[测试2] Fidelity / FBTC")
        print("-" * 40)
        page2 = await context.new_page()
        spider2 = ArkhamSpider("https://intel.arkm.com/explorer/entity/fidelity")
        results2 = await spider2.crawl(page2)
        await page2.close()

        if results2:
            print(f"✅ 获取 {len(results2)} 条数据:")
            for r in results2:
                print(f"   [{r['type']}] value={r['value']:,.2f}")
        else:
            print("❌ 未获取到数据")

        # ── 汇总 ─────────────────────────────────────────────
        print("\n" + "=" * 60)
        all_results = results1 + results2
        if all_results:
            print(f"✅ 总计: {len(all_results)} 条指标")
            print("\n📊 指标摘要:")
            for r in all_results:
                t = r["type"]
                v = r["value"]
                if "btc" in t:
                    print(f"   {t}: {v:,.0f} BTC")
                elif "eth" in t:
                    print(f"   {t}: {v:,.0f} ETH")
                elif "usd" in t:
                    print(f"   {t}: ${v/1e9:.2f}B")
        else:
            print("⚠️  所有爬虫均未获取到数据")
            print("提示: 可能是网络限制或页面结构变化，请检查截图")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    finally:
        if browser:
            await browser.close()
        if playwright_inst:
            await playwright_inst.stop()


if __name__ == "__main__":
    asyncio.run(main())
