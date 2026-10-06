-- =============================================================================
-- 13 · Know the panel: who is in it, what it sees, and whether that bends the results
-- -----------------------------------------------------------------------------
-- Every number in this analysis is a panel number, so the panel itself is
-- checked like any other data source:
--   panel_profile      size, activity concentration, extreme users, mirror ids
--   panel_coverage     which major sites the panel sees. It is not a uniform
--                      sample of browsing: Google, YouTube, Facebook and Amazon
--                      are almost absent, while PayPal, MSN, Walmart and the NYT are
--                      large. Shares of "all browsing" are therefore meaningless;
--                      only within-site measures are valid, and each audience
--                      needs its own calibration (08).
--   hijack_by_segment  does the Walmart hijacking result depend on the kind of
--                      panelist? Panels are often recruited through browser
--                      extensions, so coupon-extension users may be
--                      over-represented, and a few heavy users can dominate.
--                      The result is recomputed by segment and with
--                      coupon-extension users down-weighted.
-- =============================================================================

-- Activity per person (all events of the day, US and non-US)
CREATE OR REPLACE TABLE panel_activity AS
SELECT user_id, events,
       CASE WHEN events <= 21   THEN '1 Light (≤ median)'
            WHEN events <= 141  THEN '2 Mid (to p90)'
            WHEN events <= 600  THEN '3 Heavy (p90–p99)'
            WHEN events <= 5000 THEN '4 Very heavy (> p99)'
            ELSE                     '5 Extreme (> 5,000 events)'
       END AS activity_tier
FROM panel_users;

CREATE OR REPLACE TABLE panel_profile AS
WITH ranked AS (
    SELECT events, row_number() OVER (ORDER BY events DESC) AS rk, count(*) OVER () AS n, sum(events) OVER () AS tot
    FROM panel_users
)
SELECT (SELECT count(*) FROM panel_users)                                         AS panel_user_ids,
       (SELECT count(*) FROM user_alias)                                          AS mirror_ids_merged_brand_users,
       (SELECT count_if(is_us) FROM panel_users)                                  AS us_user_ids,
       round(100.0 * (SELECT count_if(is_us) FROM panel_users) / (SELECT count(*) FROM panel_users), 1) AS pct_us,
       (SELECT quantile_cont(events, 0.5)  FROM panel_users)                      AS events_p50,
       (SELECT quantile_cont(events, 0.9)  FROM panel_users)                      AS events_p90,
       (SELECT quantile_cont(events, 0.99) FROM panel_users)                      AS events_p99,
       (SELECT max(events) FROM panel_users)                                      AS events_max,
       round(100.0 * sum(events) FILTER (WHERE rk <= n * 0.01) / max(tot), 1)     AS pct_events_top1pct_users,
       round(100.0 * sum(events) FILTER (WHERE rk <= n * 0.10) / max(tot), 1)     AS pct_events_top10pct_users,
       (SELECT count(*) FROM panel_users WHERE events > 5000)                     AS users_over_5000_events,
       (SELECT round(count(DISTINCT session_id) * 1.0 / count(DISTINCT user_id), 2) FROM brand_user_events)
                                                                                  AS sessions_per_brand_user
FROM ranked;

-- Users per major site in the panel. Sites absent from the panel read ~0.
CREATE OR REPLACE TABLE panel_coverage AS
SELECT s.site, s.kind, coalesce(count(DISTINCT r.user_id), 0) AS panel_users
FROM (VALUES
    ('google.com', 'Search'), ('bing.com', 'Search'), ('youtube.com', 'Video / social'), ('facebook.com', 'Video / social'),
    ('tiktok.com', 'Video / social'), ('amazon.com', 'Retail'), ('ebay.com', 'Retail'), ('target.com', 'Retail'),
    ('walmart.com', 'Retail'), ('temu.com', 'Retail'), ('shein.com', 'Retail'), ('paypal.com', 'Payments'),
    ('msn.com', 'News / portal'), ('nytimes.com', 'News / portal'), ('cnn.com', 'News / portal'),
    ('foxnews.com', 'News / portal'), ('weather.com', 'News / portal'),
    ('capitaloneshopping.com', 'Coupon / cash-back'), ('rakuten.com', 'Coupon / cash-back'),
    ('slickdeals.net', 'Coupon / cash-back'), ('joinhoney.com', 'Coupon / cash-back'), ('retailmenot.com', 'Coupon / cash-back')
) AS s(site, kind)
LEFT JOIN raw_clicks r ON r.host = s.site
GROUP BY s.site, s.kind
ORDER BY panel_users DESC;

-- Walmart hijacking result by panelist segment ---------------------------------------
CREATE OR REPLACE TABLE coupon_extension_users AS
SELECT DISTINCT user_id FROM brand_user_events WHERE regexp_matches(host, coupon_host_re());

CREATE OR REPLACE TABLE hijack_by_segment AS
WITH k AS (
    SELECT c.*, x.user_id IS NOT NULL AS coupon_user, a.activity_tier
    FROM us_clicks c
    LEFT JOIN coupon_extension_users x USING (user_id)
    JOIN panel_activity a USING (user_id)
    WHERE c.brand = 'Walmart'
),
seg AS (
    SELECT 'Coupon / cash-back user' AS dimension,
           CASE WHEN coupon_user THEN 'Yes' ELSE 'No' END AS segment, *
    FROM k
    UNION ALL
    SELECT 'Activity tier', activity_tier, * FROM k
)
SELECT dimension, segment,
       count(DISTINCT user_id)                                                                  AS users,
       count(*)                                                                                 AS clicks,
       round(100.0 * count_if(strong_hijack_signal) / count(*), 1)                              AS pct_clicks_flagged,
       count_if(converted)                                                                      AS orders,
       round(100.0 * count_if(converted AND strong_hijack_signal) / nullif(count_if(converted), 0), 1)
                                                                                                AS pct_orders_flagged
FROM seg
GROUP BY dimension, segment
ORDER BY dimension, segment;

-- Down-weighting coupon-extension users: what if the panel holds them at 2× or 4×
-- their population rate, or they are dropped entirely (weight 0)?
CREATE OR REPLACE TABLE hijack_reweighted AS
WITH k AS (
    SELECT c.converted, c.strong_hijack_signal, x.user_id IS NOT NULL AS coupon_user
    FROM us_clicks c LEFT JOIN coupon_extension_users x USING (user_id)
    WHERE c.brand = 'Walmart'
)
SELECT w.label AS coupon_user_weight,
       round(100.0 * sum(CASE WHEN coupon_user THEN w.w ELSE 1 END) FILTER (WHERE converted AND strong_hijack_signal)
                   / sum(CASE WHEN coupon_user THEN w.w ELSE 1 END) FILTER (WHERE converted), 1) AS pct_orders_flagged
FROM k
CROSS JOIN (VALUES (1.0, '1 (as observed)'), (0.5, '0.5 (panel holds them at 2x)'),
                   (0.25, '0.25 (at 4x)'), (0.0, '0 (dropped)')) AS w(w, label)
GROUP BY w.w, w.label
ORDER BY w.w DESC;
