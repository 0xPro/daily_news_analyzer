# main.py
# The Orchestrator: links the Curator skill (Skill A) to the Analyst skill (Skill B).

import json
import os

from tools.news_fetcher import fetch_news
from tools.price_auditor import audit_prices
from tools.telegram_sender import send_message


def load_config(path: str = "config.json") -> dict:
    """Load configuration from a JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def run_curator(config: dict) -> list[dict]:
    """Run the Curator skill: fetch and cache relevant news articles."""
    tickers = config.get("watchlist", [])
    articles = fetch_news(tickers, config)

    cache_dir = os.path.join("data", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "articles.json")
    with open(cache_path, "w") as f:
        json.dump(articles, f, indent=2)

    print(f"[Curator] Cached {len(articles)} articles to {cache_path}")
    return articles


def run_analyst(articles: list[dict], config: dict) -> None:
    """Run the Analyst skill: analyze articles, audit prices, write theses, and notify."""
    tickers = config.get("watchlist", [])
    prices = audit_prices(tickers, config)

    theses_dir = os.path.join("data", "theses")
    os.makedirs(theses_dir, exist_ok=True)

    report_lines: list[str] = ["# Daily News Analysis\n"]

    for ticker in tickers:
        relevant = [a for a in articles if a.get("ticker") == ticker]
        price = prices.get(ticker, "N/A")

        thesis_lines = [
            f"# {ticker} Thesis\n",
            f"**Current Price:** {price}\n",
            f"**Relevant Articles:** {len(relevant)}\n",
        ]
        for article in relevant:
            thesis_lines.append(f"- [{article.get('title')}]({article.get('url')})\n")

        thesis_path = os.path.join(theses_dir, f"{ticker}.md")
        with open(thesis_path, "w") as f:
            f.writelines(thesis_lines)

        print(f"[Analyst] Wrote thesis for {ticker} to {thesis_path}")
        report_lines.extend(thesis_lines)
        report_lines.append("\n---\n")

    report = "".join(report_lines)
    success = send_message(report, config)
    if success:
        print("[Orchestrator] Report delivered via Telegram.")
    else:
        print("[Orchestrator] Telegram delivery skipped (not yet configured).")


def main() -> None:
    config = load_config()
    articles = run_curator(config)
    run_analyst(articles, config)


if __name__ == "__main__":
    main()
