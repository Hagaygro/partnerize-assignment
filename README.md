# Saatva Affiliate Performance & Attribution Hijacking Analysis

Home assignment for the Senior Data Analyst position at Partnerize.

**Business question:** how does Saatva's affiliate program in the US compare with its main
competitors (Nectar, Helix, DreamCloud, Walmart)? For each brand we estimate US affiliate
clicks and the conversions they produced. We then recommend how Saatva can grow its program
and reduce fraud, focusing on attribution hijacking.

## Results at a glance

The dataset covers one day, **2026-05-01 (UTC)**. All figures are for US users. US estimates
are per day, as panel counts × a scale factor (see *Scaling to the US*).

| Brand | Network | Panel visits | Panel affiliate clicks | % visits from affiliate | Est. US affiliate clicks / day (95% CI) | Panel converted clicks | Est. US converted clicks / day |
|---|---|---:|---:|---:|---|---:|---|
| **Saatva** | Partnerize | 25 | 5 | 16.0% | **5.4k** (1.8k – 12.7k) | 0 | 27 – 109 ¹ |
| Nectar | Impact | 51 | 4 | 3.9% | 4.4k (1.2k – 11.2k) | 0 | 22 – 87 ¹ |
| Helix | Impact | 19 | 2 | 10.5% | 2.2k (0.2k – 7.9k) | 0 | 11 – 44 ¹ |
| DreamCloud | Impact | 27 | 2 | 7.4% | 2.2k (0.2k – 7.9k) | 0 | 11 – 44 ¹ |
| Walmart | Impact | 16,401 | 6,449 | 6.4% | 7.0M ² | 112 (1.74%) | 122k |

¹ No mattress-brand order was completed in the panel that day. The range applies the mattress
e-commerce conversion benchmark (0.5–2%) to the estimated clicks.
² Walmart averages 6.3 clicks per clicking user, because creator storefronts link to many products.
The share of visits that start with an affiliate click (6.4%) is the more comparable measure.

An external check agrees: Similarweb ranks affiliate as Saatva's #1 traffic channel (23.7%) and
Helix's #1 (21.0%). Nectar and DreamCloud lead with paid search, and so do their panel visits
(43% and 37% of visits).

**Hijacking, measured where the volume allows it (Walmart, 6,449 clicks):** 26% of affiliate
clicks carry a strong hijacking signal, and they account for **79% of affiliate-attributed
orders**. Clicks injected while the buyer was already in the cart or checkout convert at
**9.6%**, against 0.4% for clicks with no indicator. The median time from click to order is
**2.3 minutes**: these clicks intercept purchases that were already happening.

## Approach

```
48.4M raw events ──(03) users who touched a brand domain, deduplicated──▶ 1.64M events (3.4%)
      │                                                                    │
      │                            (04) affiliate clicks   (05) visits & sources   (06) orders
      │                                        └────────────(07) hijack indicators per click
      └──(02) data validation    (08) US users + scale factor ──▶ (09) result tables
```

* **Efficiency.** One pass over the Parquet files selects the users who touched any of the
  five brands. Everything after that runs on 3.4% of the data. The whole pipeline takes
  about 26 s on a laptop (DuckDB, 48M rows).
* **Affiliate click.** A landing on the brand's main site whose URL carries network tracking
  parameters. Partnerize: `click_id=1100l…`, `utm_medium=affiliate`. Impact: `CIDIMP`,
  `irgwc=1`, `utm_medium=AFF`. Walmart: `veh=aff`, `wmlspartner=imp_<publisher>`. CJ, Rakuten,
  Awin, ShareASale and AvantLink parameters are included too. Networks append these parameters
  on the redirect, so they survive even when the redirect hop is not recorded. Clicks are
  deduplicated on the network click id: one click shows up on ~1.4 rows, through reloads,
  parallel tabs and mirror IDs.
* **Conversion.** A visit to the brand's order-confirmation page (`walmart.com/thankyou`,
  Shopify `…/thank-you`, Magento `/checkout/onepage/success`, …), matched on the URL path.
  It is credited to the user's last affiliate click for that brand earlier the same day.
* **Visit.** A user's pageviews on a brand's main site, split by a 30-minute gap. The entry
  URL's parameters give the visit's traffic source.
* **US users.** The data has no country field. A user is non-US if ≥20% of their events are on
  non-US country domains (`.uk`, `.ca`, `.in`, `.ru`, …). 88.5% of users are US.

## Scaling to the US

The panel is a sample of users. US estimate = panel count × **F**:

* **F = 1,089 (primary): anchor-site calibration.** Similarweb shows 581.7M walmart.com
  visits/month, 95.2% from the US, or 17.9M US visits/day. The panel has 16,401 US visits to
  walmart.com that day.
* **Validation.** F applied to the mattress sites gives 35–50% of their Similarweb
  visits. The gap is consistent across brands. Two likely causes: Similarweb's latest month is
  August, the Labor Day mattress sale season, while our data is an ordinary May day; and the
  panel may cover mattress shoppers less well.
* **Range.** Calibrating each brand on its own Similarweb traffic gives the upper estimate
  (`est_us_affiliate_clicks_brand_calibrated`, e.g. Saatva 13.7k/day). Population scaling
  (324M US internet users ÷ 694k US panel users, F = 467) gives a lower one.
* **Intervals.** The 95% intervals cover only the panel's Poisson sampling error (Byar's
  approximation), not the error in F. With 2–5 clicks per mattress brand, the intervals
  overlap, so **one panel day cannot rank the mattress brands by click volume**. The
  affiliate *share* of each brand's traffic is the more robust comparison.

## Data quality findings

| Check | Finding | Handling |
|---|---|---|
| Period | One day only, 2026-05-01 00:00–23:59 UTC | Estimates are per day; orders are attributed within the day |
| Nulls / IDs | No nulls; `_ID` unique (48,395,506 rows) | — |
| Double-recorded events | 14.7% of rows repeat user + second + URL | Deduplicated |
| **Mirror user IDs** | Some people are recorded under two `USER_ID`s, one a partial copy of the other. Example: one affiliate click under two IDs. 14–28% of brand visits and 20% of orders were mirrors | User ids sharing ≥3 identical (second, URL) events are merged into one person (2,426 ids) |
| Non-page rows | iframes and tags are recorded too (`sgtm.saatva.com`, Shopify web-pixel sandboxes) | Visits use main-site pages only |
| Sessions | ~2.5 parallel `SESSION_ID`s per user per day (per tab) | Analysis is per user, not per session |
| Hourly profile | Activity jumps at 12:00 UTC (2.5% → 4.9% of rows) and drops at 18:00 (7.8% → 5.4%). Likely a collection artefact rather than behaviour | Daily totals only; no intraday conclusions |

## Attribution-hijacking indicators (per affiliate click)

| Indicator | Definition | Tier |
|---|---|---|
| Injected at cart/checkout | User was in the brand's cart/checkout in the 30 min before the click | Strong |
| Already on site | User was on the brand's site, without an affiliate tag, in the 30 min before | Strong |
| Publisher-bought search ad | The affiliate landing carries a Google/Bing ad click id (`gclid`, `gad_source`, …) | Strong (policy) |
| Brand search before | A search for the brand name within 60 s before | Medium |
| Coupon / cash-back before | A coupon or cash-back site or extension fired within 60 s before | Medium |
| Multi-brand burst | Landings on 2+ other advertisers within ±2 min. Counts as stuffing only if the user never engages; a listicle opened in tabs looks the same | Review |
| No visible referrer | No activity in the 30 min before (also true for app and email clicks) | Weak |

## Repository layout

```
sql/                       # the analysis, run in order (each file documents its logic)
  01_raw_view.sql          # view over the Parquet files
  02_data_quality.sql      # validation profile
  03_brand_user_events.sql # working dataset: brand users' events, deduplicated, mirror IDs merged
  04_affiliate_clicks.sql  # affiliate landings → deduplicated clicks, network, publisher
  05_brand_visits.sql      # visits and entry traffic source
  06_conversions.sql       # order confirmations, last-click attribution, checkout reach
  07_hijacking_signals.sql # per-click attribution-hijacking indicators
  08_us_scaling.sql        # US users, external benchmarks, scale factor + validation
  09_summary.sql           # result tables
scripts/
  download_data.py         # parallel, resumable download of the archive
  extract_data.py          # extracts the Parquet files, verifies CRCs
  run_pipeline.py          # runs sql/ in order with row-count checks, exports outputs/
outputs/                   # aggregated result tables (CSV)
data/                      # local only (git-ignored): archive, Parquet files, DuckDB database
```

## How to run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/download_data.py   # ~9.5 GB
.venv/bin/python scripts/extract_data.py    # -> data/raw/*.parquet (~12.6 GB)
.venv/bin/python scripts/run_pipeline.py    # ~30 s; tables in data/analysis.duckdb, CSVs in outputs/
```

The data is not committed to the repository. It was provided for this assignment only, and
it is too large for git.

## External sources

* Similarweb website pages, retrieved 2026-10-04 (latest month: Aug 2026):
  [walmart.com](https://www.similarweb.com/website/walmart.com/),
  [saatva.com](https://www.similarweb.com/website/saatva.com/),
  [nectarsleep.com](https://www.similarweb.com/website/nectarsleep.com/),
  [dreamcloudsleep.com](https://www.similarweb.com/website/dreamcloudsleep.com/),
  [helixsleep.com](https://www.similarweb.com/website/helixsleep.com/)
* US internet users: [DataReportal, Digital 2026](https://datareportal.com/reports/digital-2026-six-billion-internet-users)
* Mattress e-commerce conversion rates: [Grips Intelligence](https://gripsintelligence.com/insights/retailers/us-mattress.com)
  (us-mattress.com, mattressfirmep.com, mattressfirm.com retailer pages)

## Limitations and next steps

* **One day of panel data.** Mattress brands have 2–5 affiliate clicks and no completed orders.
  Next: run the same pipeline on 30–90 days, and on Saatva's own Partnerize click and order
  logs, which cover every click rather than a sample.
* **Scaling** depends on public traffic estimates for a different month. Next: calibrate on
  same-period figures (paid Similarweb / Partnerize benchmarks), and break the panel down by
  device.
* **Conversion window.** Mattresses are a considered purchase: the same-day window misses orders
  placed days after the click, while affiliate cookies last 30 days. Next: multi-day user journeys.
* **Hijacking indicators** are behavioural proxies. Next: validate them against
  Partnerize-confirmed fraud or reversal flags, and tune the thresholds.
