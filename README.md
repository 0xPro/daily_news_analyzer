# daily_news_analyzer
monorepo for daily news analyzer with learning feature

`tools/news_fetcher.py` collects news from configured sources and writes the filtered result set used by the analyzer.

## `tools/news_fetcher.py`

The script reads source definitions from `config["news_api"]["sources"]` or `config["news_sources"]`.

Supported source types:
- `{"type": "rss", "url": "..."}`
- `{"type": "url", "url": "..."}`
- `{"type": "twitter", "handle": "..."}`
- `{"type": "text_folder", "path": "data/news"}`

Each fetched item is normalized into a single-line article record with:
- `source`
- `title`
- `content` (first 500 characters)
- `url`
- `published_at`
- `ticker`

Output is written to `data/cache/[YYYYMMDDHH]-filtered.json` unless `news_output_dir` is configured.

### Text folder input

For `text_folder` sources, every non-empty `.txt` line is treated as one news item.

This supports both:
- plain headline/news lists where each line is a standalone update
- grouped desk notes such as sector headers followed by ticker headlines

Section headings like `Technology` or `Defense / Energy / Industrials` are ignored, while ticker lines like `$BA – Boeing – Won a $326M Army contract` are ingested normally.

### Example config

```json
{
  "news_api": {
    "sources": [
      { "type": "rss", "url": "https://example.com/feed.xml", "name": "Example Feed" },
      { "type": "url", "url": "https://example.com/news" },
      { "type": "twitter", "handle": "btcnews" },
      { "type": "text_folder", "path": "data/news" }
    ]
  }
}
```
