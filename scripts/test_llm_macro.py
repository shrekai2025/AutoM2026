"""
Test script for LLM Macro Strategy Integration
"""
import asyncio
import sys
sys.path.insert(0, '.')

async def main():
    from strategies import MacroStrategy
    from core.llm_service import llm_service
    
    print("=" * 50)
    print("LLM Macro Strategy Test")
    print("=" * 50)
    
    # Check LLM service
    print(f"\n[1] LLM Service Enabled: {llm_service.is_enabled()}")
    if not llm_service.is_enabled():
        print("    ⚠️ LLM is disabled. Set OPENROUTER_API_KEY in .env")
        return
    
    # Create strategy with LLM enabled
    config = MacroStrategy.get_default_config()
    config["use_llm"] = True
    
    strategy = MacroStrategy(config)
    print(f"\n[2] Strategy Created: {strategy}")
    print(f"    use_llm = {config['use_llm']}")
    
    # Run analysis
    print("\n[3] Running Analysis (this may take 10-30 seconds)...")
    result = await strategy.analyze()
    
    print(f"\n[4] Result:")
    print(f"    Signal: {result.signal.value}")
    print(f"    Score: {result.conviction_score:.1f}")
    print(f"    Reason: {result.reason}")
    print(f"\n[5] Process Logs:")
    for log in result.logs:
        print(f"    - {log['step']}: {log['output']}")
        if "LLM" in log['step']:
            print(f"      Details: {log['details'][:100]}...")
    
    print("\n✅ Test Complete!")

if __name__ == "__main__":
    asyncio.run(main())
