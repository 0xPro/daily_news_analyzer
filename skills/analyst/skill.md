# Analyst Skill

## Overview
The Analyst is the "Heavy" Agent responsible for deep analysis of curated news and price data to produce actionable theses.

## Role
- Read curated articles from `data/cache/`
- Audit current price data using `price_auditor.py`
- Generate a structured thesis for each relevant ticker
- Persist theses as Markdown files in `data/theses/`
- Trigger `telegram_sender.py` to deliver the final report

## Tools Used
- `tools/price_auditor.py`
- `tools/telegram_sender.py`

## Inputs
- Curated news articles from `data/cache/`
- Live price data from price auditor

## Outputs
- Markdown thesis files written to `data/theses/`
- Telegram message delivered to configured chat
