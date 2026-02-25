import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from config.settings import FRED_API_KEY
from data_collectors.fred_collector import fred_collector

async def verify():
    print(f"🔑 FRED_API_KEY: {FRED_API_KEY[:4]}...{FRED_API_KEY[-4:] if FRED_API_KEY else 'None'}")
    
    if not FRED_API_KEY:
        print("❌ API Key missing!")
        return

    print("📡 Fetching FRED Data...")
    try:
        data = await fred_collector.get_macro_data()
        print("\n✅ Data Received:")
        for k, v in data.items():
            print(f"   - {k}: {v}")
            
        if all(v is not None for v in data.values()):
            print("\n🎉 All indicators fetched successfully!")
        else:
            print("\n⚠️ Some indicators are missing (this might be normal if markets are closed or data is delayed).")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
