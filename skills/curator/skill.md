# Curator Skill

## Overview
The Curator is the "Light" Agent responsible for fetching and filtering daily news headlines relevant to the watchlist tickers.

## Role
- Fetch news from configured sources using `news_fetcher.py`
- Filter and rank headlines by relevance to watched assets
- Pass curated articles to the Analyst for deeper evaluation

## Tools Used
- `tools/news_fetcher.py`

## Inputs
- `config.json` watchlist of tickers/assets
- Raw news feed from news sources

## Outputs
- Filtered list of relevant news articles (written to `data/cache/`)
