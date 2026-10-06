"""Fetch daily US Google Trends interest for the five brands (Apr–Sep 2026).

Usage:
    pip install pytrends
    .venv/bin/python scripts/fetch_google_trends.py   # -> external/google_trends_us_daily.csv

Used by sql/12_seasonality.sql to move the Similarweb calibration (August) to the
panel's day (1 May). Each series is scaled 0-100 on its own by Google, so only
ratios within one series are meaningful. Fetched once and committed, so the
pipeline does not depend on the (unofficial, rate-limited) Trends endpoint.
"""
import os
import time

import pandas as pd
from pytrends.request import TrendReq

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "external", "google_trends_us_daily.csv")
# search term per brand; "nectar" alone is mostly the drink, so the mattress brands use "<brand> mattress"
TERMS = {"Saatva": "saatva", "Nectar": "nectar mattress", "Helix": "helix mattress",
         "DreamCloud": "dreamcloud mattress", "Walmart": "walmart"}


def main():
    trends = TrendReq(hl="en-US", tz=0)
    series = {}
    for brand, term in TERMS.items():
        trends.build_payload([term], timeframe="2026-04-01 2026-09-30", geo="US")
        series[brand] = trends.interest_over_time()[term]
        time.sleep(2)
    df = pd.DataFrame(series)
    df.index.name = "day"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT)
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(df)} days")


if __name__ == "__main__":
    main()
