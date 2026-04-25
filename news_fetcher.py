"""
Stock-targeted news fetcher using yfinance.
Replaces RSS feeds — every article is already relevant to the stocks we trade.
"""
import time
import yfinance as yf
from datetime import datetime, timedelta
from config import STOCK_UNIVERSE, POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS, THEME_DETECTORS
from rich.console import Console

console = Console()

# Module-level cache so we fetch each ticker's news only once per analysis run
_NEWS_CACHE: dict[str, list[dict]] = {}


def _parse_item(item: dict, symbol: str) -> dict | None:
    """Parse a yfinance news item — handles both old and new API formats."""
    try:
        # New format (yfinance ≥ 0.2.50): item['content'] sub-dict
        if "content" in item:
            c = item["content"]
            return {
                "title":   c.get("title", ""),
                "summary": c.get("summary", ""),
                "link":    (c.get("canonicalUrl") or {}).get("url", ""),
                "source":  (c.get("provider") or {}).get("displayName", ""),
                "published": c.get("pubDate", ""),
                "symbol":  symbol,
            }
        # Old format: flat dict with direct keys
        return {
            "title":   item.get("title", ""),
            "summary": item.get("summary", ""),
            "link":    item.get("link", ""),
            "source":  item.get("publisher", ""),
            "published": str(item.get("providerPublishTime", "")),
            "symbol":  symbol,
        }
    except Exception:
        return None


def fetch_stock_news(symbol: str, max_count: int = 10) -> list[dict]:
    """Fetch yfinance news for one symbol. Cached per analysis run."""
    if symbol in _NEWS_CACHE:
        return _NEWS_CACHE[symbol]
    try:
        raw = yf.Ticker(symbol).news or []
        articles = []
        for item in raw[:max_count]:
            parsed = _parse_item(item, symbol)
            if parsed and parsed["title"]:
                articles.append(parsed)
        _NEWS_CACHE[symbol] = articles
    except Exception:
        _NEWS_CACHE[symbol] = []
    return _NEWS_CACHE[symbol]


def fetch_all_news(max_age_days: int = 7) -> list[dict]:
    """
    Fetch news for every stock in the universe via yfinance.
    Returns only articles directly relevant to stocks we trade — no noise.
    """
    all_articles: list[dict] = []
    seen_titles: set[str] = set()
    total = len(STOCK_UNIVERSE)

    for i, symbol in enumerate(STOCK_UNIVERSE, 1):
        console.print(f"  [dim]news [{i}/{total}] {symbol}[/dim]", end="\r")
        for art in fetch_stock_news(symbol):
            key = art["title"][:80]
            if key and key not in seen_titles:
                seen_titles.add(key)
                all_articles.append(art)
        time.sleep(0.08)

    console.print()
    return all_articles


# ── Sentiment ────────────────────────────────────────────────────────────────

def score_sentiment(text: str) -> float:
    text_lower = text.lower()
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


# Stock name aliases — yfinance already targets articles, but cross-reference helps
_NAME_MAP: dict[str, list[str]] = {
    "HDFCBANK":   ["HDFC Bank", "HDFCBANK"],
    "ICICIBANK":  ["ICICI Bank", "ICICIBANK"],
    "SBIN":       ["SBI", "State Bank"],
    "TCS":        ["TCS", "Tata Consultancy"],
    "INFY":       ["Infosys", "INFY"],
    "WIPRO":      ["Wipro"],
    "BHARTIARTL": ["Airtel", "Bharti"],
    "HINDUNILVR": ["HUL", "Hindustan Unilever"],
    "BAJFINANCE": ["Bajaj Finance"],
    "KOTAKBANK":  ["Kotak"],
    "LT":         ["L&T", "Larsen"],
    "MARUTI":     ["Maruti", "Suzuki"],
    "TATAMOTORS": ["Tata Motors"],
    "TATASTEEL":  ["Tata Steel"],
    "TATAPOWER":  ["Tata Power"],
    "INDHOTEL":   ["Indian Hotels", "Taj Hotels", "IHCL"],
    "INTERGLOBE": ["IndiGo", "InterGlobe"],
    "MARICO":     ["Marico", "Parachute"],
    "COLPAL":     ["Colgate", "Palmolive"],
    "DLF":        ["DLF"],
    "RVNL":       ["RVNL", "Rail Vikas"],
    "IRFC":       ["IRFC", "Indian Railway Finance"],
    "MAZAGON":    ["Mazagon", "MDL"],
    "ASHOKLEY":   ["Ashok Leyland"],
    "BHARATFORG": ["Bharat Forge"],
    "KPITTECH":   ["KPIT"],
    "COFORGE":    ["Coforge"],
}


def get_stock_sentiment(symbol: str, articles: list[dict]) -> dict:
    """Filter pre-fetched articles for a specific stock and compute sentiment."""
    base = symbol.replace(".NS", "").replace(".BO", "").replace("&", "AND")
    search_terms = _NAME_MAP.get(base, [base])

    # Primary: articles directly tagged to this symbol by yfinance
    relevant = [a for a in articles if a.get("symbol") == symbol]

    # Secondary: cross-reference by name mention in other stocks' articles
    seen = {a["title"][:60] for a in relevant}
    for art in articles:
        if art.get("symbol") == symbol:
            continue
        combined = (art["title"] + " " + art.get("summary", "")).lower()
        if any(t.lower() in combined for t in search_terms):
            key = art["title"][:60]
            if key not in seen:
                seen.add(key)
                relevant.append(art)

    if not relevant:
        return {"symbol": symbol, "article_count": 0, "sentiment": 0.0, "articles": []}

    sentiments = [score_sentiment(a["title"] + " " + a.get("summary", "")) for a in relevant]
    return {
        "symbol":        symbol,
        "article_count": len(relevant),
        "sentiment":     round(sum(sentiments) / len(sentiments), 3),
        "articles":      [{"title": a["title"], "source": a.get("source", "")} for a in relevant[:5]],
    }


def fetch_event_news(
    keywords: list[str],
    extra_feeds: list[str] | None = None,
    max_age_days: int = 3,
) -> list[dict]:
    """
    Search the targeted stock news corpus for articles matching event keywords.
    extra_feeds is accepted for backward compatibility but ignored.
    """
    all_news = fetch_all_news(max_age_days)
    keywords_lower = [kw.lower() for kw in keywords]
    matched: list[dict] = []
    seen: set[str] = set()

    for art in all_news:
        combined = (art["title"] + " " + art.get("summary", "")).lower()
        match_count = sum(1 for kw in keywords_lower if kw in combined)
        if match_count == 0:
            continue
        key = art["title"][:60]
        if key not in seen:
            seen.add(key)
            matched.append({**art, "match_count": match_count})

    matched.sort(key=lambda x: x["match_count"], reverse=True)
    return matched


def auto_detect_themes(articles: list[dict]) -> dict[str, dict]:
    """Scan article corpus for pre-defined market themes."""
    texts = [(a["title"] + " " + a.get("summary", "")).lower() for a in articles]
    total = len(texts)
    detected: dict[str, dict] = {}

    for theme, cfg in THEME_DETECTORS.items():
        keywords  = cfg["keywords"]
        threshold = cfg["threshold"]
        hit_count = 0
        matched_kw: set[str] = set()
        for text in texts:
            for kw in keywords:
                if kw in text:
                    hit_count += 1
                    matched_kw.add(kw)
                    break
        effective_threshold = max(threshold, int(total * 0.03))
        if hit_count >= effective_threshold:
            detected[theme] = {
                "hits":             hit_count,
                "matched_keywords": list(matched_kw)[:5],
                "impacts":          cfg["impacts"],
                "sectors_affected": list({s for s, _, _ in cfg["impacts"]}),
            }

    return detected


def get_market_sentiment(articles: list[dict]) -> dict:
    all_sentiments = [score_sentiment(a["title"] + " " + a.get("summary", "")) for a in articles]
    if not all_sentiments:
        return {"overall_sentiment": 0.0, "total_articles": 0}
    return {
        "overall_sentiment": round(sum(all_sentiments) / len(all_sentiments), 3),
        "total_articles":    len(all_sentiments),
        "positive_count":    sum(1 for s in all_sentiments if s > 0),
        "negative_count":    sum(1 for s in all_sentiments if s < 0),
    }
