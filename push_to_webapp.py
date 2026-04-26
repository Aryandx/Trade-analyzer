"""
Push latest analysis results to the webapp public directory.
Run after: python main.py
Usage: python push_to_webapp.py
"""
import json
import os
import shutil

BASE   = os.path.dirname(os.path.abspath(__file__))
SRC    = os.path.join(BASE, "results", "latest_analysis.json")
DST    = os.path.join(BASE, "webapp", "public", "data", "analysis.json")


def main():
    if not os.path.exists(SRC):
        print("No analysis found. Run: python main.py  first.")
        return

    os.makedirs(os.path.dirname(DST), exist_ok=True)

    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    # Inject simplified sparkline data (last 30 closes from cache if present)
    # Since main.py excludes _price_cache from saved JSON, we load from cache files
    cache_dir = os.path.join(BASE, "results", "cache")
    if os.path.isdir(cache_dir):
        import pandas as pd
        sparklines = {}
        for pick in data.get("top_picks", []):
            sym = pick["symbol"]
            cache_path = os.path.join(cache_dir, f"{sym.replace('.', '_')}.parquet")
            if os.path.exists(cache_path):
                try:
                    df = pd.read_parquet(cache_path)
                    sparklines[sym] = df["close"].tail(30).round(2).tolist()
                except Exception:
                    pass
        data["sparklines"] = sparklines

    # Inject current prices for all universe stocks (from cache)
    current_prices: dict = {}
    for pick in data.get("top_picks", []):
        sym = pick["symbol"].replace(".NS", "")
        current_prices[sym] = pick["price"]
    if os.path.isdir(cache_dir):
        try:
            import pandas as pd
            from config import STOCK_UNIVERSE
            for sym in STOCK_UNIVERSE:
                base = sym.replace(".NS", "")
                if base in current_prices:
                    continue
                cache_path = os.path.join(cache_dir, f"{sym.replace('.', '_')}.parquet")
                if os.path.exists(cache_path):
                    try:
                        df = pd.read_parquet(cache_path)
                        if not df.empty:
                            current_prices[base] = round(float(df["close"].iloc[-1]), 2)
                    except Exception:
                        pass
        except ImportError:
            pass
    data["current_prices"] = current_prices

    with open(DST, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    size = os.path.getsize(DST) / 1024
    print(f"Synced analysis to webapp ({size:.0f} KB): {DST}")
    print(f"  {len(data.get('top_picks', []))} top picks")
    print(f"  {len(data.get('sparklines', {}))} sparklines")
    print()
    print("Next steps:")
    print("  cd webapp && npm run dev    # local preview")
    print("  git add . && git commit -m 'update analysis' && git push")


if __name__ == "__main__":
    main()
