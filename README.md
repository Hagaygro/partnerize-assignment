# Saatva Affiliate Performance & Attribution Hijacking Analysis

Home assignment for the Senior Data Analyst position at Partnerize.

**Business question:** how does Saatva's affiliate program in the US compare with its main
competitors (Nectar, Helix, DreamCloud, Walmart)? For each brand we estimate US affiliate
clicks and the conversions they produced. We then recommend how Saatva can grow its program
and reduce fraud, focusing on attribution hijacking.

## Results at a glance

The dataset covers one day, **2026-05-01 (UTC)**. All figures are for US users. US estimates
are per day, as panel counts × a scale factor calibrated on the brand's own audience (see
*Scaling to the US*).

| Brand | Network | Panel visits | % visits from affiliate | Panel affiliate clicks | Est. US affiliate clicks / day (95% CI) | Conservative est. ¹ | Panel converted clicks | Est. US converted clicks / day |
|---|---|---:|---:|---:|---|---:|---:|---|
| **Saatva** | Partnerize | 25 | 16.0% | 6 ² | **16.7k** (6.1k – 36.4k) | 6.5k | 0 | 84 – 334 ³ |
| Nectar | Impact | 51 | 3.9% | 4 | 11.1k (3.0k – 28.5k) | 4.4k | 0 | 56 – 223 ³ |
| Helix | Impact | 19 | 10.5% | 2 | 5.6k (0.6k – 20.1k) | 2.2k | 0 | 28 – 111 ³ |
| DreamCloud | Impact | 27 | 7.4% | 2 | 5.6k (0.6k – 20.1k) | 2.2k | 0 | 28 – 111 ³ |
| Walmart | Impact | 16,401 | 6.4% | 6,449 | 7.0M ⁴ | 3.0M | 111 (1.72%) | 121k |

¹ Mattress brands scaled with the walmart.com-calibrated factor; Walmart with the population ratio.
² Five clicks that landed on saatva.com, plus one Partnerize click that never loaded the site
(cookie stuffing by a browser extension; see below).
³ No mattress-brand order, registration or financing application followed an affiliate click
that day. The range applies the mattress e-commerce conversion benchmark (0.5–2%) to the
estimated clicks.
⁴ Walmart averages 6.4 clicks per clicking user, because creator storefronts link to many products.
The share of visits that start with an affiliate click (6.4%) is the more comparable measure.

**External checks.** Similarweb ranks affiliate as Saatva's #1 traffic channel (23.7%), or about
16k US affiliate visits/day. The panel-based estimate is 16.7k clicks/day; the scale is partly
calibrated on the same source, so this is a consistency check, not independent proof. Similarweb also ranks
affiliate #1 for Helix (21.0%), and paid search #1 for Nectar and DreamCloud. Their panel visits
lean the same way: 43% and 37% of visits come from paid search.

**Hijacking.**

* **In Saatva's own program**, 2 of 6 clicks carry a strong signal:
  * A *"new tab" browser extension* (`newtab.club` → `tatrck.com/clickGate`) fired a Partnerize
    click for Saatva (`saatva.prf.hn`, `camref:1011laqH9`). saatva.com never loaded: the user
    was browsing Sleep Number at the time.
  * A publisher named as an *email* partner (`brandxemail`) delivered its click through a
    *Google ad* (`gad_source=1`) to `/sale`, with an auto-applied coupon.
* **Where the volume allows it (Walmart, 6,449 clicks)**, the clicks with a strong signal are
  13–24% of affiliate clicks but **52–79% of affiliate-attributed orders**. The range depends on
  the look-back window (2–30 min; see `hijack_sensitivity`).
* **Clicks fired after the buyer had already viewed the cart or checkout** (within 30 min)
  convert at **13%**, or 15% within 2 min, against 0.4% for clicks with no indicator. The median
  time from click to order is **2.3 minutes**. 258 of them had a walmart.com page as the previous
  event, a median of 2 seconds earlier, with no publisher page in between: a silent redirect.
* **Those clicks add no orders.** The obvious objection is that buyers in the cart convert anyway. It is
  tested in `11_incrementality.sql`. Each US Walmart shopper's stage (first cart view, or first checkout
  view) is fixed before any click, and shoppers an affiliate brought to the cart are excluded. Shoppers who then got
  an affiliate click order at the same rate as those who did not: 34% vs 32% after the cart,
  67% vs 76% after checkout. Across the 56 shoppers who got a click, **25 ordered; 25.7 would have without
  it** (ratio 0.97, 95% CI 0.63–1.44, so at most ~31% of these orders could be incremental).
* **Commission at risk.** Clicks fired at the cart carry half of Walmart's affiliate-attributed orders (~61k
  US orders/day). At a $100–125 average order and 1–4% commission, that is **$22M–111M a year** paid for
  sales that were already happening. Saatva's panel has no orders to measure its own share. Every 10% of
  Saatva's affiliate orders that is hijacked costs about **$80k–1.05M a year** ($860 average order,
  3–10% commission, 84–334 affiliate orders/day).

## Approach

```
48.4M raw events ──(03) users who touched a brand, deduplicated, mirror IDs merged──▶ 1.64M events (3.4%)
      │                                                                              │
      │           (04) affiliate clicks: tagged landings + redirect hops   (05) visits & sources
      │           (06) orders, registrations, financing, funnel      (07) hijack indicators per click
      └──(02) data validation   (08) US users + scale factors ──▶ (09) result tables ──▶ (10) sensitivity
                                                                                      └──▶ (11) incrementality, $ at risk
```

* **Efficiency.** One pass over the Parquet files selects the users who touched any of the
  five brands. Everything after that runs on 3.4% of the data. The whole pipeline takes
  about 30 s on a laptop (DuckDB, 48M rows).
* **Affiliate click.** Detected along two paths:
  1. **A tagged landing**: a landing on the brand's main site whose URL carries network
     tracking parameters. Partnerize: `click_id=1100l…`, `utm_medium=affiliate`. Impact:
     `CIDIMP`, `irgwc=1`, `utm_medium=AFF`. Walmart: `veh=aff`, `wmlspartner=imp_<publisher>`.
     CJ, Rakuten, Awin, ShareASale and AvantLink parameters are included too. Clicks are
     deduplicated on the network click id: one click shows up on ~1.4 rows, through reloads,
     parallel tabs and mirror IDs.
  2. **A network redirect hop** pointing at the brand (`saatva.prf.hn/click/…`,
     `goto.walmart.com/c/…`). The brand's full `.com` domain must appear in the hop: an earlier
     version matched `walmart.ca` and gift-card pages. A hop followed by a tagged landing is the
     same click. A hop with no landing registered a click without the user seeing the site.
* **Conversion**, in two levels, following the assignment's definition ("payment, purchase,
  registration, or any other meaningful completion event"):
  * *Primary*: a completed order, i.e. the order-confirmation page (`walmart.com/thankyou`,
    Shopify `…/thank-you`, Magento `/checkout/onepage/success`, …), matched on the URL path.
  * *Broad*: an order, an account registration, or a financing application (Affirm, Klarna, …).

  A conversion is credited to the user's last affiliate click for that brand earlier the same
  day. Cart and checkout reach are tracked as funnel steps.
* **Visit.** A user's pageviews on a brand's main site, split by a 30-minute gap. The entry
  URL's parameters give the visit's traffic source.
* **US users.** The data has no country field. A user is non-US if ≥20% of their events are on
  non-US country domains (`.uk`, `.ca`, `.in`, `.ru`, …). 88.5% of users are US.

## Scaling to the US

The panel is a sample of users. US estimate = panel count × **F**, where F is calibrated on a site
with public traffic figures: its true daily US visits ÷ the panel's US visits to it.

* **The panel does not cover every audience equally.** Calibrated on walmart.com (Similarweb:
  581.7M visits/month, 95.2% US → 17.9M US visits/day; panel: 16,401), F = 1,089. That factor
  puts the mattress sites at only 35–50% of their own Similarweb traffic.
* **So each brand is scaled with the factor of its own audience:**
  * Walmart: **F_retail = 1,089**.
  * The mattress brands: **F_mattress = 2,784**, pooled over Saatva, Nectar and DreamCloud (103
    panel visits → 287k Similarweb US visits/day). Helix has no public visit figure. Checked one
    brand at a time, F_mattress reproduces each brand's Similarweb traffic at 0.89–1.27×.
* **Alternatives** are reported as the conservative estimate: F_retail for the mattress brands,
  and the population ratio for Walmart (324M US internet users ÷ 694k US panel users = 467).
* **Caveat.** Similarweb's latest public month is August, the Labor Day mattress sale season.
  F_mattress may therefore overstate an ordinary May day somewhat.
* **Intervals.** The 95% intervals cover only the panel's Poisson sampling error (Byar's
  approximation), not the error in F. With 2–6 clicks per mattress brand, the intervals
  overlap, so **one panel day cannot rank the mattress brands by click volume**. The affiliate
  *share* of each brand's traffic is the more robust comparison.

## Data quality findings

| Check | Finding | Handling |
|---|---|---|
| Period | One day only, 2026-05-01 00:00–23:59 UTC | Estimates are per day; conversions are attributed within the day |
| Nulls / IDs | No nulls; `_ID` unique (48,395,506 rows) | — |
| Double-recorded events | 14.7% of rows repeat user + second + URL | Deduplicated |
| **Mirror user IDs** | Some people are recorded under two `USER_ID`s, one a partial copy of the other. Example: one affiliate click under two IDs. 14–28% of brand visits and 20% of orders were mirrors | User ids sharing ≥3 identical (second, URL) events are merged into one person (2,426 ids) |
| Non-page rows | iframes and tags are recorded too (`sgtm.saatva.com`, Shopify web-pixel sandboxes) | Visits use main-site pages only |
| Redirect hops | Rarely recorded: 10 hop rows for the five brands | Counted as clicks when no tagged landing follows |
| Sessions | ~2.5 parallel `SESSION_ID`s per user per day (per tab) | Analysis is per person, not per session |
| URL encoding | Some URLs carry non-UTF8 escapes (e.g. GBK search terms) | Decoding wrapped in `try()` |
| Hourly profile | Activity jumps at 12:00 UTC (2.5% → 4.9% of rows) and drops at 18:00 (7.8% → 5.4%). Likely a collection artefact rather than behaviour | Daily totals only; no intraday conclusions |

## Attribution-hijacking indicators (per affiliate click)

| Indicator | Definition | Tier |
|---|---|---|
| Click without landing | The network registered a click, but the brand's site never loaded (cookie stuffing) | Strong |
| Injected at cart/checkout | User was in the brand's cart/checkout in the 30 min before the click | Strong |
| Already on site | User was on the brand's site, without an affiliate tag, in the 30 min before | Strong |
| Publisher-bought search ad | The affiliate landing carries a Google/Bing ad click id (`gclid`, `gad_source`, …) | Strong (policy) |
| Brand search before | A search for the brand name within 60 s before | Medium |
| Coupon / cash-back before | A coupon or cash-back site or extension fired within 60 s before | Medium |
| Multi-brand burst | Landings on 2+ other advertisers within ±2 min. Counts as stuffing only if the user never engages; a listicle opened in tabs looks the same | Review |
| No visible referrer | No activity in the 30 min before (also true for app and email clicks) | Weak |

The 30-minute look-back is tested at 10 and 2 minutes in `10_sensitivity.sql`:

| Walmart, look-back | % of clicks flagged | % of affiliate orders from flagged clicks | Conversion rate: flagged vs other |
|---|---:|---:|---|
| 30 min | 23.6% | 79.3% | 5.8% vs 0.5% |
| 10 min | 18.8% | 72.1% | 6.6% vs 0.6% |
| 2 min | 13.3% | 52.3% | 6.8% vs 1.0% |

## Repository layout

```
sql/                       # the analysis, run in order (each file documents its logic)
  01_raw_view.sql          # view over the Parquet files
  02_data_quality.sql      # validation profile
  03_brand_user_events.sql # working dataset: brand users' events, deduplicated, mirror IDs merged
  04_affiliate_clicks.sql  # tagged landings + redirect hops → deduplicated clicks, network, publisher
  05_brand_visits.sql      # visits and entry traffic source
  06_conversions.sql       # orders, registrations, financing, funnel; last-click attribution
  07_hijacking_signals.sql # per-click attribution-hijacking indicators
  08_us_scaling.sql        # US users, external benchmarks, scale factors + validation
  09_summary.sql           # result tables
  10_sensitivity.sql       # hijack indicators under stricter look-back windows
  11_incrementality.sql    # do clicks fired at the cart add orders? + commission at risk
scripts/
  download_data.py         # parallel, resumable download of the archive
  extract_data.py          # extracts the Parquet files, verifies CRCs
  run_pipeline.py          # runs sql/ in order with row-count checks, exports outputs/
outputs/                   # aggregated result tables (CSV)
deck/
  build_deck.py            # builds the presentation from outputs/*.csv
  saatva_affiliate_analysis.pptx   # the deck: upload to Google Drive, open with Google Slides
data/                      # local only (git-ignored): archive, Parquet files, DuckDB database
```

## How to run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/download_data.py   # ~9.5 GB
.venv/bin/python scripts/extract_data.py    # -> data/raw/*.parquet (~12.6 GB)
.venv/bin/python scripts/run_pipeline.py    # ~30 s; tables in data/analysis.duckdb, CSVs in outputs/
.venv/bin/python deck/build_deck.py         # -> deck/saatva_affiliate_analysis.pptx
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
* Average order value, retrieved 2026-10-06: [walmart.com](https://gripsintelligence.com/insights/retailers/walmart.com)
  ($100–125, Mar 2026) and [saatva.com](https://gripsintelligence.com/insights/retailers/saatva.com) ($850–875, Jun 2026), Grips Intelligence
* Commission rates: Walmart affiliate program 1–4% by category ([Lasso summary](https://getlasso.co/affiliate/walmart/));
  Saatva 3% base ([LinkClicky](https://linkclicky.com/affiliate-program/saatva/)), 10% partner program ([ACA](https://www.acatoday.org/practice-resources/saatva-mattress/saatva10percent/))
* Mattress e-commerce conversion rates: [Grips Intelligence](https://gripsintelligence.com/insights/retailers/us-mattress.com)
  (us-mattress.com, mattressfirmep.com, mattressfirm.com retailer pages)

## Limitations and next steps

* **One day of panel data.** Mattress brands have 2–6 affiliate clicks and no completed orders.
  Next: run the same pipeline on 30–90 days, and on Saatva's own Partnerize click and order
  logs, which cover every click rather than a sample.
* **Scaling** depends on public traffic estimates for a different month. Next: calibrate on
  same-period figures (paid Similarweb / Partnerize benchmarks), and break the panel down by
  device.
* **Conversion window.** Mattresses are a considered purchase: the same-day window misses orders
  placed days after the click, while affiliate cookies last 30 days. Next: multi-day user journeys.
* **Hijacking indicators** are behavioural proxies, and the strongest evidence comes from
  Walmart's volume. Next: validate them against Partnerize-confirmed fraud or reversal flags,
  run holdout tests for incrementality, and tune the thresholds.
