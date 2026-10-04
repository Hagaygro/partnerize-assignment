-- =============================================================================
-- 10 · Sensitivity of the hijacking indicators
-- -----------------------------------------------------------------------------
-- The "already on site" and "injected at cart/checkout" indicators look back 30
-- minutes. A user who viewed the cart 25 minutes earlier and then genuinely read a
-- review before clicking is flagged too. To check that the headline does not
-- depend on that choice, the strong signal is recomputed with the look-back
-- tightened to 10 and 2 minutes. Stuffed clicks (no landing) and publisher-bought
-- search ads do not depend on a window.
--
-- Read: if flagged clicks still convert far above the rest, and still account for
-- most affiliate-credited orders at 2 minutes, the result is robust.
-- =============================================================================

CREATE OR REPLACE TABLE hijack_sensitivity AS
WITH windows AS (
    SELECT *
    FROM (VALUES (1800, '30 min (base)'), (600, '10 min'), (120, '2 min')) AS t(secs, look_back)
),
flagged AS (
    SELECT w.secs, w.look_back, c.brand, c.converted, c.click_time, c.conversion_time,
           coalesce(c.secs_since_checkout <= w.secs, FALSE)                    AS checkout_flag,
           c.no_landing OR c.has_paid_search_click_id
               OR coalesce(c.secs_since_checkout   <= w.secs, FALSE)
               OR coalesce(c.secs_since_brand_page <= w.secs, FALSE)           AS strong_flag
    FROM us_clicks c
    CROSS JOIN windows w
)
SELECT brand,
       look_back,
       count(*)                                                                                   AS clicks,
       round(100.0 * count_if(strong_flag) / count(*), 1)                                         AS pct_clicks_strong,
       round(100.0 * count_if(strong_flag AND converted) / nullif(count_if(strong_flag), 0), 2)   AS cr_strong_pct,
       round(100.0 * count_if(NOT strong_flag AND converted)
                   / nullif(count_if(NOT strong_flag), 0), 2)                                     AS cr_other_pct,
       round(100.0 * count_if(strong_flag AND converted) / nullif(count_if(converted), 0), 1)     AS pct_orders_from_strong,
       round(100.0 * count_if(checkout_flag) / count(*), 1)                                       AS pct_clicks_checkout,
       round(100.0 * count_if(checkout_flag AND converted) / nullif(count_if(checkout_flag), 0), 2) AS cr_checkout_pct,
       round(median(date_diff('second', click_time, conversion_time))
             FILTER (WHERE checkout_flag AND converted) / 60.0, 1)                                AS median_min_to_order_checkout
FROM flagged
GROUP BY brand, look_back, secs
ORDER BY brand, secs DESC;
