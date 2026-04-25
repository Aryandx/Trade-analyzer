import re
import time
import requests
import feedparser
from datetime import datetime, timedelta
from config import NEWS_RSS_FEEDS, POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS, THEME_DETECTORS
from rich.console import Console

console = Console()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_all_news(max_age_days: int = 7) -> list[dict]:
    all_articles = []
    cutoff = datetime.now() - timedelta(days=max_age_days)

    for feed_url in NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:40]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                published = entry.get("published", "")
                link = entry.get("link", "")
                all_articles.append({
                    "title": title,
                    "summary": summary[:500],
                    "published": published,
                    "link": link,
                    "source": feed_url.split("/")[2],
                })
        except Exception as e:
            console.print(f"[yellow]RSS feed error ({feed_url}): {e}[/yellow]")
        time.sleep(0.5)

    return all_articles


def score_sentiment(text: str) -> float:
    text_lower = text.lower()
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def get_stock_sentiment(symbol: str, articles: list[dict]) -> dict:
    # Extract base name from symbol (e.g., "RELIANCE" from "RELIANCE.NS")
    base = symbol.replace(".NS", "").replace(".BO", "").replace("&", "AND")
    # Also try common name mappings
    name_map = {
        "HDFCBANK": ["HDFC Bank", "HDFCBANK"],
        "ICICIBANK": ["ICICI Bank", "ICICIBANK"],
        "SBIN": ["SBI", "State Bank"],
        "TCS": ["TCS", "Tata Consultancy"],
        "INFY": ["Infosys", "INFY"],
        "WIPRO": ["Wipro"],
        "BHARTIARTL": ["Airtel", "Bharti"],
        "HINDUNILVR": ["HUL", "Hindustan Unilever"],
        "BAJFINANCE": ["Bajaj Finance"],
        "KOTAKBANK": ["Kotak"],
        "LT": ["L&T", "Larsen"],
        "MARUTI": ["Maruti"],
        "TATAMOTORS": ["Tata Motors"],
        "TATASTEEL": ["Tata Steel"],
        "TATAPOWER": ["Tata Power"],
        "IRCTC": ["IRCTC"],
        "HAL": ["HAL", "Hindustan Aeronautics"],
        "BEL": ["BEL", "Bharat Electronics"],
    }
    search_terms = name_map.get(base, [base])

    relevant = []
    for art in articles:
        combined = (art["title"] + " " + art["summary"]).lower()
        if any(term.lower() in combined for term in search_terms):
            relevant.append(art)

    if not relevant:
        return {"symbol": symbol, "article_count": 0, "sentiment": 0.0, "articles": []}

    sentiments = [score_sentiment(a["title"] + " " + a["summary"]) for a in relevant]
    avg_sentiment = round(sum(sentiments) / len(sentiments), 3)

    return {
        "symbol": symbol,
        "article_count": len(relevant),
        "sentiment": avg_sentiment,
        "articles": [{"title": a["title"], "source": a["source"]} for a in relevant[:5]],
    }


def fetch_event_news(
    keywords: list[str],
    extra_feeds: list[str] | None = None,
    max_age_days: int = 3,
) -> list[dict]:
    """
    Fetch news articles matching any of the given keywords from standard + extra RSS feeds.
    Returns filtered list of relevant articles sorted by relevance (match count desc).
    """
    feeds = list(NEWS_RSS_FEEDS) + (extra_feeds or [])
    cutoff = datetime.now() - timedelta(days=max_age_days)
    keywords_lower = [kw.lower() for kw in keywords]

    all_articles = []
    seen_titles: set[str] = set()

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:50]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                combined = (title + " " + summary).lower()

                match_count = sum(1 for kw in keywords_lower if kw in combined)
                if match_count == 0:
                    continue

                title_key = title[:60]
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                all_articles.append({
                    "title": title,
                    "summary": summary[:500],
                    "link": link,
                    "source": feed_url.split("/")[2],
                    "match_count": match_count,
                })
        except Exception as e:
            console.print(f"[yellow]Event feed error ({feed_url}): {e}[/yellow]")
        time.sleep(0.3)

    all_articles.sort(key=lambda x: x["match_count"], reverse=True)
    return all_articles


def auto_detect_themes(articles: list[dict]) -> dict[str, dict]:
    """
    Scan all articles for pre-defined themes. Any theme whose keywords appear
    >= threshold times in the article corpus is considered active.
    Returns {theme_name: {hits, impacts, sectors_affected}}.
    """
    # Build one large lowercased text blob per article
    texts = [(a["title"] + " " + a["summary"]).lower() for a in articles]
    total = len(texts)

    detected: dict[str, dict] = {}
    for theme, cfg in THEME_DETECTORS.items():
        keywords  = cfg["keywords"]
        threshold = cfg["threshold"]

        hit_count = 0
        matched_kw = set()
        for text in texts:
            for kw in keywords:
                if kw in text:
                    hit_count += 1
                    matched_kw.add(kw)
                    break   # count each article once per theme

        # Scale threshold: more articles = slightly higher bar
        effective_threshold = max(threshold, int(total * 0.03))
        if hit_count >= effective_threshold:
            detected[theme] = {
                "hits":            hit_count,
                "matched_keywords": list(matched_kw)[:5],
                "impacts":         cfg["impacts"],
                "sectors_affected": list({s for s, _, _ in cfg["impacts"]}),
            }

    return detected


def get_market_sentiment(articles: list[dict]) -> dict:
    all_sentiments = [score_sentiment(a["title"] + " " + a["summary"]) for a in articles]
    if not all_sentiments:
        return {"overall_sentiment": 0.0, "total_articles": 0}
    return {
        "overall_sentiment": round(sum(all_sentiments) / len(all_sentiments), 3),
        "total_articles": len(articles),
        "positive_count": sum(1 for s in all_sentiments if s > 0),
        "negative_count": sum(1 for s in all_sentiments if s < 0),
    }
