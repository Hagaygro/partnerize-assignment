-- =============================================================================
-- 09 · Results tables (US panel users only)
-- -----------------------------------------------------------------------------
-- competitor_summary   one row per brand: traffic, affiliate clicks, outcomes, US estimates
-- traffic_mix          share of each brand's visits by entry source
-- publisher_summary    one row per brand × publisher, with outcome and hijack indicators
--
-- US estimates = panel count × the brand's scale factor (08: F_mattress for the
-- mattress brands, F_retail for Walmart); `_alt` uses the alternative factor
-- (F_retail for mattress brands, the population ratio for Walmart). The 95%
-- intervals cover the Poisson sampling error of the panel count only (Byar's
-- approximation), not the error in F.
-- =============================================================================

CREATE OR REPLACE MACRO poisson_lo(n) AS
    CASE WHEN n = 0 THEN 0.0 ELSE n * pow(1 - 1 / (9.0 * n) - 1.96 / (3 * sqrt(n)), 3) END;
CREATE OR REPLACE MACRO poisson_hi(n) AS
    (n + 1) * pow(1 - 1 / (9.0 * (n + 1)) + 1.96 / (3 * sqrt(n + 1)), 3);

CREATE OR REPLACE TABLE us_clicks AS
SELECT c.*,
       o.converted, o.converted_broad, o.conversion_time,
       o.reached_cart, o.reached_checkout, o.registered, o.applied_financing,
       r.primary_signal, r.strong_hijack_signal, r.no_landing, r.multi_brand_burst,
       r.in_checkout_before, r.already_on_site, r.secs_since_checkout, r.secs_since_brand_page,
       r.brand_search_60s, r.coupon_ext_60s, r.no_referrer, r.prev_host, r.secs_since_prev
FROM affiliate_clicks c
JOIN click_outcomes o USING (brand, click_key)
JOIN click_risk r     USING (brand, click_key)
WHERE c.user_id IN (SELECT user_id FROM panel_users WHERE is_us);

CREATE OR REPLACE TABLE competitor_summary AS
WITH visits AS (
    SELECT brand,
           count(*)                      AS visits,
           count_if(affiliate_entry)     AS affiliate_entry_visits
    FROM brand_visits
    WHERE user_id IN (SELECT user_id FROM panel_users WHERE is_us)
    GROUP BY brand
),
clicks AS (
    SELECT brand,
           string_agg(DISTINCT network, ', ')                 AS networks,
           count(*)                                           AS clicks,
           count_if(no_landing)                               AS clicks_no_landing,
           count(DISTINCT user_id)                            AS click_users,
           count(DISTINCT publisher)                          AS publishers,
           count_if(reached_cart OR reached_checkout)         AS clicks_to_cart_or_checkout,
           count_if(converted)                                AS converted_clicks,
           count_if(converted_broad)                          AS converted_clicks_broad,
           count_if(strong_hijack_signal)                     AS strong_signal_clicks
    FROM us_clicks
    GROUP BY brand
),
orders AS (
    SELECT brand, count(*) AS conversions_all_sources
    FROM conversions
    WHERE user_id IN (SELECT user_id FROM panel_users WHERE is_us)
    GROUP BY brand
)
SELECT b.brand,
       b.is_client,
       c.networks,
       -- panel (one day, US users)
       coalesce(v.visits, 0)                                                          AS panel_visits,
       coalesce(c.clicks, 0)                                                          AS panel_affiliate_clicks,
       coalesce(c.clicks_no_landing, 0)                                               AS panel_clicks_no_landing,
       coalesce(c.click_users, 0)                                                     AS panel_affiliate_users,
       coalesce(c.publishers, 0)                                                      AS panel_publishers,
       coalesce(c.converted_clicks, 0)                                                AS panel_converted_clicks,
       coalesce(c.converted_clicks_broad, 0)                                          AS panel_converted_clicks_broad,
       coalesce(o.conversions_all_sources, 0)                                         AS panel_conversions_all_sources,
       -- rates
       round(100.0 * v.affiliate_entry_visits / nullif(v.visits, 0), 1)               AS pct_visits_from_affiliate,
       round(100.0 * c.clicks_to_cart_or_checkout / nullif(c.clicks, 0), 1)           AS pct_clicks_reaching_cart_or_checkout,
       round(100.0 * c.converted_clicks / nullif(c.clicks, 0), 2)                     AS pct_clicks_converting,
       round(100.0 * c.converted_clicks / nullif(o.conversions_all_sources, 0), 1)    AS pct_orders_affiliate_attributed,
       round(100.0 * c.strong_signal_clicks / nullif(c.clicks, 0), 1)                 AS pct_clicks_strong_hijack_signal,
       -- US estimates per day
       round(f.scale_factor)                                                          AS scale_factor,
       round(coalesce(c.clicks, 0) * f.scale_factor)                                  AS est_us_affiliate_clicks,
       round(poisson_lo(coalesce(c.clicks, 0)) * f.scale_factor)                      AS est_us_affiliate_clicks_lo95,
       round(poisson_hi(coalesce(c.clicks, 0)) * f.scale_factor)                      AS est_us_affiliate_clicks_hi95,
       round(coalesce(c.clicks, 0) * f.scale_factor_alt)                              AS est_us_affiliate_clicks_alt,
       round(coalesce(c.converted_clicks, 0) * f.scale_factor)                        AS est_us_converted_clicks,
       round(poisson_hi(coalesce(c.converted_clicks, 0)) * f.scale_factor)            AS est_us_converted_clicks_hi95,
       -- Converting clicks per day from the benchmark conversion range, where the panel has too few orders
       CASE WHEN coalesce(c.converted_clicks, 0) < 10
            THEN round(coalesce(c.clicks, 0) * f.scale_factor * mattress_cr_low()) END  AS est_us_converted_clicks_benchmark_lo,
       CASE WHEN coalesce(c.converted_clicks, 0) < 10
            THEN round(coalesce(c.clicks, 0) * f.scale_factor * mattress_cr_high()) END AS est_us_converted_clicks_benchmark_hi
FROM brands b
JOIN brand_scale f  ON f.brand = b.brand
LEFT JOIN visits v  ON v.brand = b.brand
LEFT JOIN clicks c  ON c.brand = b.brand
LEFT JOIN orders o  ON o.brand = b.brand
ORDER BY b.is_client DESC, panel_affiliate_clicks DESC;

CREATE OR REPLACE TABLE traffic_mix AS
SELECT brand, entry_source,
       count(*)                                                                 AS visits,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY brand), 1)     AS pct_of_brand_visits
FROM brand_visit_sources
WHERE user_id IN (SELECT user_id FROM panel_users WHERE is_us)
GROUP BY brand, entry_source
ORDER BY brand, visits DESC;

CREATE OR REPLACE TABLE publisher_summary AS
SELECT brand,
       network,
       publisher,
       count(*)                                                AS clicks,
       count(DISTINCT user_id)                                 AS users,
       round(count(*) / count(DISTINCT user_id), 1)            AS clicks_per_user,
       count_if(reached_cart OR reached_checkout)              AS clicks_to_cart_or_checkout,
       count_if(converted)                                     AS converted_clicks,
       count_if(no_landing)                                    AS no_landing,
       count_if(in_checkout_before)                            AS injected_at_checkout,
       count_if(already_on_site)                               AS already_on_site,
       count_if(has_paid_search_click_id)                      AS paid_search_click_id,
       count_if(brand_search_60s)                              AS brand_search_before,
       count_if(coupon_ext_60s)                                AS coupon_before,
       count_if(multi_brand_burst)                             AS burst,
       count_if(no_referrer)                                   AS no_referrer,
       round(100.0 * count_if(strong_hijack_signal) / count(*), 1) AS pct_strong_signal,
       any_value(publisher_sub_id)                             AS example_sub_id,
       any_value(coupon)                                       AS example_coupon
FROM us_clicks
GROUP BY brand, network, publisher
ORDER BY brand, clicks DESC;
