# daily_news_analyzer
monorepo for daily news analyzer with learning feature

`tools/news_fetcher.py` reads configured entries from `config["news_api"]["sources"]` (or `config["news_sources"]`) and supports:
- `{"type": "rss", "url": "..."}`
- `{"type": "url", "url": "..."}`
- `{"type": "twitter", "handle": "..."}`
- `{"type": "text_folder", "path": "data/news"}` where each `.txt` line is one news item

Fetched items are cleaned into a single line, truncated to the first 500 content characters, and saved to `data/cache/[YYYYMMDDHH]-filtered.json` unless `news_output_dir` is configured.
