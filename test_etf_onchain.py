"""
ETF 链上监控采集器测试脚本

运行: python test_etf_onchain.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def main():
    from data_collectors.etf_onchain_collector import ETFOnchainCollector
    collector = ETFOnchainCollector()

    print("=" * 60)
    print("测试 1: yfinance ETF AUM 查询")
    print("=" * 60)
    # 单独测试 IBIT (数据量小，速度快)
    aum = await collector.get_etf_aum("IBIT")
    if aum:
        print(f"✅ IBIT AUM: ${aum/1e9:.2f}B")
    else:
        print("❌ IBIT AUM: 无数据（可能 yfinance 暂时不可用）")

    aum_gbtc = await collector.get_etf_aum("GBTC")
    if aum_gbtc:
        print(f"✅ GBTC AUM: ${aum_gbtc/1e9:.2f}B")
    else:
        print("❌ GBTC AUM: 无数据")

    aum_etha = await collector.get_etf_aum("ETHA")
    if aum_etha:
        print(f"✅ ETHA AUM: ${aum_etha/1e9:.2f}B")
    else:
        print("❌ ETHA AUM: 无数据")

    print()
    print("=" * 60)
    print("测试 2: mempool.space BTC 地址余额")
    print("=" * 60)
    # 使用已验证的大额 Legacy P2PKH 地址
    test_btc_addr = "1FeexV6bAHb8ybZjqQMjJrcCrHGW9sb6uF"  # 公知大额地址
    bal = await collector.get_btc_address_balance(test_btc_addr)
    if bal is not None and bal > 0:
        print(f"✅ Legacy地址余额: {bal:,.4f} BTC")
    elif bal == 0:
        print(f"✅ mempool.space API正常，余额为 0")
    else:
        print("❌ mempool.space 查询失败")

    print()
    print("=" * 60)
    print("测试 3: Blockscout ETH 地址余额")
    print("=" * 60)
    # Vitalik 公开地址（有很多 ETH）
    test_eth_addr = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
    eth_bal = await collector.get_eth_address_balance(test_eth_addr)
    if eth_bal is not None:
        print(f"✅ Vitalik 地址余额: {eth_bal:.2f} ETH —— blockscout.com API 可用")
    else:
        print("❌ Blockscout 查询失败（可能需要 API Key 或速率限制）")

    print()
    print("=" * 60)
    print("测试 4: macro_indicators 卡片格式化")
    print("=" * 60)
    cards = await collector.get_macro_indicators(btc_price=95000, eth_price=3500)
    if cards:
        print(f"✅ 生成 {len(cards)} 张指标卡片:")
        for card in cards:
            print(f"   [{card['abbr']}] {card['name_zh']}: {card['value']}")
    else:
        print("⚠️  未生成任何卡片（数据源全部失败）")

    await collector.close()
    print()
    print("测试完成！")


if __name__ == "__main__":
    asyncio.run(main())
