-- =============================================================================
-- 06 · Conversions and click → conversion attribution
-- -----------------------------------------------------------------------------
-- A conversion is a completed order: a visit to the brand's order-confirmation
-- page. Each brand's pattern was checked against the URLs present in the data:
--   Walmart     walmart.com/thankyou
--   Shopify     /checkouts/…/thank-you (also fired by the checkout's web-pixel iframe)
--   Magento     /checkout/onepage/success
--   generic     /thank-you, /order-confirmation, /checkout/confirmation …
-- Any brand subdomain counts (e.g. checkout.helixsleep.com).
-- Reaching the cart or checkout is kept as a funnel proxy: on a single day,
-- completed mattress orders are too few to compare brands on their own.
--
-- Attribution: last click, within the same day (the data covers one day). A click
-- converts if the same user reaches the brand's confirmation page after it and
-- before any later affiliate click to that brand.
-- =============================================================================

CREATE OR REPLACE MACRO conversion_re() AS
    '(?i)/(thank[-_]?you|thankyou|checkout/onepage/success|checkout/success|checkout/confirmation|order[-_]?confirmation|order[-_]?complete|purchase/confirmation)(/|\?|#|$)';

CREATE OR REPLACE MACRO checkout_re() AS
    '(?i)/(cart|checkout|checkouts|basket)(/|\?|#|$)';

-- Patterns are matched on the URL path only, so a "/thankyou" inside a query
-- string (e.g. a return_url parameter) does not count.
CREATE OR REPLACE MACRO url_path(u) AS
    regexp_extract(u, '^[a-z]+://[^/?#]+([^?#]*)', 1);

CREATE OR REPLACE TABLE conversion_events AS
SELECT brand, user_id, created_time, host, url
FROM brand_user_events
WHERE brand IS NOT NULL
  AND regexp_matches(url_path(url), conversion_re());

-- One conversion per user per brand per 30 min. The confirmation page often
-- fires several rows (reloads, iframes).
CREATE OR REPLACE TABLE conversions AS
WITH ordered AS (
    SELECT *,
           date_diff('second', lag(created_time) OVER (PARTITION BY brand, user_id ORDER BY created_time),
                     created_time) AS secs_since_prev
    FROM conversion_events
)
SELECT brand, user_id, created_time AS conversion_time, url AS conversion_url
FROM ordered
WHERE secs_since_prev IS NULL OR secs_since_prev > 1800;

-- Click-level outcome --------------------------------------------------------------
CREATE OR REPLACE TABLE click_outcomes AS
WITH clicks AS (
    SELECT brand, click_key, user_id, click_time,
           lead(click_time) OVER (PARTITION BY brand, user_id ORDER BY click_time) AS next_click_time
    FROM affiliate_clicks
),
reached_checkout AS (
    SELECT c.brand, c.click_key, bool_or(TRUE) AS reached_checkout
    FROM clicks c
    JOIN brand_user_events e
      ON e.user_id = c.user_id AND e.brand = c.brand
     AND e.created_time >= c.click_time
     AND (c.next_click_time IS NULL OR e.created_time < c.next_click_time)
     AND regexp_matches(url_path(e.url), checkout_re())
    GROUP BY ALL
)
SELECT c.brand,
       c.click_key,
       min(v.conversion_time)                                   AS conversion_time,
       min(v.conversion_time) IS NOT NULL                       AS converted,
       coalesce(any_value(r.reached_checkout), FALSE)           AS reached_checkout
FROM clicks c
LEFT JOIN conversions v
       ON v.brand = c.brand AND v.user_id = c.user_id
      AND v.conversion_time >= c.click_time
      AND (c.next_click_time IS NULL OR v.conversion_time < c.next_click_time)
LEFT JOIN reached_checkout r
       ON r.brand = c.brand AND r.click_key = c.click_key
GROUP BY c.brand, c.click_key;
