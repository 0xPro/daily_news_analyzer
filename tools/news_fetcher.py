import json
import logging
import os
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.request import urlopen

try:
    import feedparser
except ImportError:  # pragma: no cover - dependency is optional at import time
    feedparser = None

try:
    from ntscraper import Nitter
except ImportError:  # pragma: no cover - dependency is optional at import time
    Nitter = None


LOGGER = logging.getLogger(__name__)
MAX_CONTENT_LENGTH = 500
MAX_TITLE_LENGTH = 80


def fetch_news(tickers: list[str], config: dict) -> list[dict]:
    """
    Fetch news articles relevant to the given tickers.

    Args:
        tickers: List of ticker symbols to search for.
        config: Configuration dictionary containing API keys and source settings.

    Returns:
        A list of article dictionaries with keys: title, url, source, published_at, ticker.
    """
    articles: list[dict] = []

    for source in _load_sources(config):
        try:
            items = _fetch_source_items(source)
        except Exception as exc:
            LOGGER.error("Failed to fetch news from %s: %s", _source_label(source), exc)
            continue

        for item in items:
            articles.extend(_match_tickers(item, tickers))

    _save_filtered_articles(articles, config)
    return articles


def _load_sources(config: dict) -> list[dict[str, Any]]:
    news_api = config.get("news_api") or {}
    raw_sources = config.get("news_sources") or news_api.get("sources") or []

    if isinstance(raw_sources, list):
        return [_normalize_source(source) for source in raw_sources]

    if not isinstance(raw_sources, dict):
        return []

    normalized: list[dict[str, Any]] = []
    for rss_url in _deduplicate(raw_sources.get("rss", []) + raw_sources.get("rss_feeds", [])):
        normalized.append({"type": "rss", "url": rss_url})
    for page_url in raw_sources.get("urls", []):
        normalized.append({"type": "url", "url": page_url})
    for handle in _deduplicate(raw_sources.get("twitter", []) + raw_sources.get("twitter_handles", [])):
        normalized.append({"type": "twitter", "handle": handle})

    text_folder = raw_sources.get("text_folder") or raw_sources.get("text_files")
    if text_folder:
        normalized.append({"type": "text_folder", "path": text_folder})

    return [_normalize_source(source) for source in normalized]


def _normalize_source(source: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        return source

    if isinstance(source, str):
        return {"type": "rss", "url": source}

    raise TypeError(f"Unsupported news source configuration: {source!r}")


def _fetch_source_items(source: dict[str, Any]) -> list[dict]:
    source_type = (source.get("type") or "rss").lower()
    if source_type == "rss":
        return _fetch_rss_items(source)
    if source_type == "url":
        return _fetch_url_items(source)
    if source_type in {"twitter", "x"}:
        return _fetch_twitter_items(source)
    if source_type in {"text", "text_folder", "text_files"}:
        return _fetch_text_items(source)

    raise ValueError(f"Unsupported source type: {source_type}")


def _fetch_rss_items(source: dict[str, Any]) -> list[dict]:
    if feedparser is None:
        raise RuntimeError("feedparser is not installed")

    source_url = source.get("url")
    if not source_url:
        raise ValueError("RSS source is missing a url")

    parsed = feedparser.parse(source_url)
    entries = parsed.get("entries", [])
    if getattr(parsed, "bozo", 0) and not entries:
        raise getattr(parsed, "bozo_exception", RuntimeError("Unable to parse RSS feed"))

    feed_title = _clean_text(source.get("name") or parsed.get("feed", {}).get("title") or source_url)
    items: list[dict] = []
    for entry in entries:
        content = (
            _first_content_value(entry.get("content"))
            or entry.get("summary")
            or entry.get("description")
            or entry.get("title")
            or ""
        )
        items.append(
            _make_article(
                source_name=feed_title,
                title=entry.get("title") or feed_title,
                content=content,
                url=entry.get("link") or source_url,
                published_at=entry.get("published") or entry.get("updated") or "",
            )
        )

    return items


def _fetch_url_items(source: dict[str, Any]) -> list[dict]:
    source_url = source.get("url")
    if not source_url:
        raise ValueError("URL source is missing a url")

    with urlopen(source_url) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(charset, errors="replace")

    content = _clean_text(_strip_tags(html))
    title = source.get("title") or _extract_html_title(html) or source_url
    return [
        _make_article(
            source_name=source.get("name") or source_url,
            title=title,
            content=content,
            url=source_url,
        )
    ]


def _fetch_twitter_items(source: dict[str, Any]) -> list[dict]:
    handle = (source.get("handle") or source.get("username") or "").lstrip("@")
    if not handle:
        raise ValueError("Twitter source is missing a handle")

    limit = int(source.get("limit") or 10)
    scraper = _get_twitter_scraper()
    result = scraper.get_tweets(handle, mode="user", number=limit)
    tweets = result.get("tweets", []) if isinstance(result, dict) else result

    items: list[dict] = []
    for tweet in tweets or []:
        text = tweet.get("text") or tweet.get("content") or ""
        link = tweet.get("link") or _tweet_url(handle, tweet)
        items.append(
            _make_article(
                source_name=source.get("name") or f"Twitter:@{handle}",
                title=_title_from_text(text, fallback=f"Tweet from @{handle}"),
                content=text,
                url=link,
                published_at=tweet.get("date") or tweet.get("published") or "",
            )
        )

    return items


def _fetch_text_items(source: dict[str, Any]) -> list[dict]:
    folder_path = source.get("path") or source.get("folder")
    if not folder_path:
        raise ValueError("Text source is missing a path")

    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Text source folder does not exist: {folder}")

    items: list[dict] = []
    for file_path in sorted(folder.glob("*.txt")):
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                cleaned_line = _clean_text(line)
                if not cleaned_line:
                    continue

                items.append(
                    _make_article(
                        source_name=source.get("name") or file_path.stem,
                        title=_title_from_text(cleaned_line, fallback=f"{file_path.name}:{line_number}"),
                        content=cleaned_line,
                        url=str(file_path),
                    )
                )

    return items


def _get_twitter_scraper():
    if Nitter is None:
        raise RuntimeError("ntscraper is not installed")

    return Nitter(log_level=1)


def _match_tickers(article: dict, tickers: list[str]) -> list[dict]:
    if not tickers:
        item = dict(article)
        item["ticker"] = None
        return [item]

    haystack = f"{article.get('title', '')} {article.get('content', '')}".lower()
    matches = [ticker for ticker in tickers if ticker.lower() in haystack]

    matched_articles: list[dict] = []
    for ticker in matches:
        item = dict(article)
        item["ticker"] = ticker
        matched_articles.append(item)

    return matched_articles


def _make_article(
    source_name: str,
    title: str,
    content: str,
    url: str = "",
    published_at: str = "",
) -> dict[str, Any]:
    cleaned_source = _clean_text(source_name) or "unknown"
    cleaned_content = _truncate(_clean_text(content), MAX_CONTENT_LENGTH)
    cleaned_title = _clean_text(title) or _title_from_text(cleaned_content, fallback=cleaned_source)

    return {
        "source": cleaned_source,
        "title": cleaned_title,
        "content": cleaned_content,
        "url": _clean_text(url),
        "published_at": _clean_text(published_at),
    }


def _save_filtered_articles(articles: list[dict], config: dict) -> None:
    output_dir = config.get("news_output_dir") or os.path.join("data", "cache")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{_current_output_stamp()}-filtered.json")

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(articles, handle, indent=2)

def _current_output_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H")


def _source_label(source: dict[str, Any]) -> str:
    return source.get("name") or source.get("url") or source.get("path") or source.get("handle") or "unknown source"


def _deduplicate(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    unique_values: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _first_content_value(content_entries: Any) -> str:
    if not isinstance(content_entries, list) or not content_entries:
        return ""

    first_item = content_entries[0]
    if isinstance(first_item, dict):
        return str(first_item.get("value") or "")

    return str(first_item)


def _extract_html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return _clean_text(match.group(1)) if match else ""


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _clean_text(text: Any) -> str:
    plain_text = unescape(str(text or ""))
    return re.sub(r"\s+", " ", _strip_tags(plain_text)).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    return text[:limit].rstrip()


def _title_from_text(text: str, fallback: str) -> str:
    cleaned_text = _clean_text(text)
    if not cleaned_text:
        return fallback

    return cleaned_text[:MAX_TITLE_LENGTH].rstrip()


def _tweet_url(handle: str, tweet: dict[str, Any]) -> str:
    tweet_id = tweet.get("tweetId") or tweet.get("id")
    if tweet_id:
        return f"https://twitter.com/{handle}/status/{tweet_id}"

    return f"https://twitter.com/{handle}"
