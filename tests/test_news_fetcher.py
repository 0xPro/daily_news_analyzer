import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.news_fetcher import MAX_CONTENT_LENGTH, fetch_news


class _FakeTwitterScraper:
    def get_tweets(self, handle: str, mode: str, number: int) -> dict:
        return {
            "tweets": [
                {
                    "text": "BTC breakout <b>incoming</b>\nwatch this space",
                    "date": "2026-03-29",
                    "id": "1",
                }
            ]
        }


class _FakeFeed(dict):
    bozo = 0


class NewsFetcherTests(unittest.TestCase):
    def test_fetch_news_combines_sources_and_writes_filtered_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "out"
            text_dir = temp_path / "txt"
            text_dir.mkdir()

            html_path = temp_path / "article.html"
            html_path.write_text(
                "<html><head><title>BTC &amp; Markets</title></head>"
                "<body><p>BTC <strong>jumps</strong> after major announcement.</p></body></html>",
                encoding="utf-8",
            )
            (text_dir / "notes.txt").write_text(
                "BTC notebook update with extra whitespace\n\nETH line should be filtered out\n",
                encoding="utf-8",
            )

            config = {
                "news_api": {
                    "sources": [
                        {"type": "url", "url": html_path.as_uri(), "name": "Local Page"},
                        {"type": "rss", "url": "https://example.com/feed.xml", "name": "RSS Feed"},
                        {"type": "twitter", "handle": "btcnews"},
                        {"type": "text_folder", "path": str(text_dir), "name": "Notes"},
                    ]
                },
                "news_output_dir": str(output_dir),
            }

            fake_feed = _FakeFeed(
                {
                    "feed": {"title": "Crypto Feed"},
                    "entries": [
                        {
                            "title": "BTC rally continues",
                            "description": "BTC price climbs<br />with strong momentum",
                            "link": "https://example.com/rss-item",
                            "published": "Sat, 29 Mar 2026 09:00:00 GMT",
                        }
                    ],
                }
            )

            with patch("tools.news_fetcher._get_twitter_scraper", return_value=_FakeTwitterScraper()), patch(
                "tools.news_fetcher.feedparser", SimpleNamespace(parse=lambda _: fake_feed)
            ), patch("tools.news_fetcher._current_output_stamp", return_value="2026032909"):
                articles = fetch_news(["BTC"], config)

            self.assertEqual(len(articles), 4)
            self.assertTrue((output_dir / "2026032909-filtered.json").exists())

            saved_articles = json.loads((output_dir / "2026032909-filtered.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_articles, articles)

            for article in articles:
                self.assertEqual(article["ticker"], "BTC")
                self.assertNotIn("\n", article["source"])
                self.assertNotIn("\n", article["title"])
                self.assertNotIn("\n", article["content"])
                self.assertLessEqual(len(article["content"]), MAX_CONTENT_LENGTH)

            self.assertEqual(articles[0]["source"], "Local Page")
            self.assertEqual(articles[0]["title"], "BTC & Markets")
            self.assertIn("BTC jumps after major announcement.", articles[0]["content"])

    def test_fetch_news_logs_errors_and_continues_with_other_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            text_dir = temp_path / "txt"
            output_dir = temp_path / "out"
            text_dir.mkdir()
            (text_dir / "notes.txt").write_text("BTC survives source failure\n", encoding="utf-8")

            config = {
                "news_api": {
                    "sources": [
                        {"type": "text_folder", "path": str(temp_path / "missing")},
                        {"type": "text_folder", "path": str(text_dir), "name": "Fallback"},
                    ]
                },
                "news_output_dir": str(output_dir),
            }

            with self.assertLogs("tools.news_fetcher", level="ERROR") as logs, patch(
                "tools.news_fetcher._current_output_stamp", return_value="2026032909"
            ):
                articles = fetch_news(["BTC"], config)

            self.assertEqual(len(articles), 1)
            self.assertEqual(articles[0]["source"], "Fallback")
            self.assertIn("Failed to fetch news", logs.output[0])
            self.assertTrue((output_dir / "2026032909-filtered.json").exists())

    def test_text_sources_skip_section_headers_and_avoid_short_ticker_false_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            text_dir = temp_path / "txt"
            output_dir = temp_path / "out"
            text_dir.mkdir()
            (text_dir / "sample.txt").write_text(
                "Defense / Energy / Industrials\n"
                "$BA – Boeing – Won a $326M Army contract\n"
                "\n"
                "Technology\n"
                "Nasdaq hits correction territory. Tech stock valuations back to the lows seen around the April 2025 tariff shock\n",
                encoding="utf-8",
            )

            config = {
                "news_api": {"sources": [{"type": "text_folder", "path": str(text_dir), "name": "Desk Notes"}]},
                "news_output_dir": str(output_dir),
            }

            with patch("tools.news_fetcher._current_output_stamp", return_value="2026032910"):
                filtered_articles = fetch_news(["BA"], config)
                all_articles = fetch_news([], config)

            self.assertEqual(len(filtered_articles), 1)
            self.assertEqual(filtered_articles[0]["title"], "$BA – Boeing – Won a $326M Army contract")

            self.assertEqual(len(all_articles), 2)
            self.assertEqual(
                [article["title"] for article in all_articles],
                [
                    "$BA – Boeing – Won a $326M Army contract",
                    "Nasdaq hits correction territory. Tech stock valuations back to the lows seen ar",
                ],
            )


if __name__ == "__main__":
    unittest.main()
