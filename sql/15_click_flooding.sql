-- =============================================================================
-- 15 · Click flooding (US panel users)
-- -----------------------------------------------------------------------------
-- A handful of people produce most of Walmart's affiliate clicks. If those
-- clicks are automated, they inflate the click estimate, and they also dilute
-- the hijacking shares: "x% of clicks take y% of orders" depends on the
-- denominator.
--
-- click_flood_behaviour  people with an affiliate click, by clicks per day: how they browse
-- click_flooding         per brand and threshold (10 / 20 / 50 clicks a day): share of
--                        clicks and orders, US estimate without them, and the hijacking
--                        shares recomputed on the remaining clicks
-- click_flood_sources    publisher and the site just before each flood click (>= 5 clicks)
--
-- The base threshold (20, macro flood_min_clicks in 07) sits where behaviour
-- changes: below it people click < 2 times an hour across 13-15 sites, above
-- it 13-15 times an hour across 6-9 sites, with almost no orders.
-- =============================================================================

CREATE OR REPLACE TABLE click_flood_behaviour AS
WITH per_person AS (
    SELECT brand, user_id,
           count(*)             AS clicks,
           count_if(converted)  AS converted_clicks
    FROM us_clicks
    GROUP BY brand, user_id
),
browsing AS (
    SELECT user_id,
           count(*)                                          AS events,
           count(DISTINCT host)                              AS sites,
           count(DISTINCT date_trunc('hour', created_time))  AS active_hours
    FROM brand_user_events
    WHERE user_id IN (SELECT user_id FROM per_person)
    GROUP BY user_id
)
SELECT p.brand,
       CASE WHEN p.clicks >= 50 THEN '5 50+'
            WHEN p.clicks >= 20 THEN '4 20-49'
            WHEN p.clicks >= 10 THEN '3 10-19'
            WHEN p.clicks >= 4  THEN '2 4-9'
            ELSE                     '1 1-3' END                         AS clicks_per_day,
       count(*)                                                           AS people,
       sum(p.clicks)                                                      AS clicks,
       sum(p.converted_clicks)                                            AS converted_clicks,
       round(100.0 * sum(p.converted_clicks) / sum(p.clicks), 2)          AS cr_pct,
       median(b.sites)                                                    AS median_sites_visited,
       median(b.active_hours)                                             AS median_active_hours,
       median(round(p.clicks / greatest(b.active_hours, 1), 1))           AS median_clicks_per_active_hour
FROM per_person p
JOIN browsing b USING (user_id)
GROUP BY ALL;

CREATE OR REPLACE TABLE click_flooding AS
WITH thresholds AS (
    SELECT * FROM (VALUES (10), (20), (50)) t(min_clicks)
),
scored AS (
    SELECT t.min_clicks, c.brand, c.converted, c.strong_hijack_signal,
           count(*) OVER (PARTITION BY t.min_clicks, c.brand, c.user_id) >= t.min_clicks  AS flood,
           c.user_id
    FROM us_clicks c
    CROSS JOIN thresholds t
)
SELECT s.brand,
       s.min_clicks || CASE WHEN s.min_clicks = flood_min_clicks() THEN ' (base)' ELSE '' END   AS threshold,
       count(DISTINCT s.user_id) FILTER (WHERE s.flood)                                      AS flood_people,
       count(*)                                                                              AS clicks,
       count_if(s.flood)                                                                     AS flood_clicks,
       round(100.0 * count_if(s.flood) / count(*), 1)                                        AS pct_clicks_flood,
       count_if(s.flood AND s.converted)                                                     AS flood_converted_clicks,
       round(100.0 * count_if(s.flood AND s.converted) / nullif(count_if(s.converted), 0), 1) AS pct_orders_flood,
       round(100.0 * count_if(s.flood AND s.converted) / nullif(count_if(s.flood), 0), 2)     AS cr_flood_pct,
       round(100.0 * count_if(NOT s.flood AND s.converted) / nullif(count_if(NOT s.flood), 0), 2) AS cr_other_pct,
       -- US estimate per day, with and without the flood clicks
       round(count(*) * any_value(f.scale_factor))                                           AS est_us_affiliate_clicks,
       round(count_if(NOT s.flood) * any_value(f.scale_factor))                              AS est_us_affiliate_clicks_excl_flood,
       -- the hijacking shares (07) on the remaining clicks
       round(100.0 * count_if(NOT s.flood AND s.strong_hijack_signal)
             / nullif(count_if(NOT s.flood), 0), 1)                                          AS pct_clicks_strong_excl_flood,
       round(100.0 * count_if(NOT s.flood AND s.strong_hijack_signal AND s.converted)
             / nullif(count_if(NOT s.flood AND s.converted), 0), 1)                          AS pct_orders_strong_excl_flood
FROM scored s
JOIN brand_scale f USING (brand)
GROUP BY s.brand, s.min_clicks;

-- Aggregated to publisher x previous site, at least 5 clicks, so no single user is exposed.
CREATE OR REPLACE TABLE click_flood_sources AS
SELECT brand,
       publisher,
       prev_host,
       count(*)                 AS flood_clicks,
       count(DISTINCT user_id)  AS people,
       count_if(converted)      AS converted_clicks,
       median(secs_since_prev)  AS median_secs_since_prev
FROM us_clicks
WHERE click_flood
GROUP BY brand, publisher, prev_host
HAVING count(*) >= 5;
