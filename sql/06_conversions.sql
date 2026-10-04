-- =============================================================================
-- 06 · Conversions and click → conversion attribution
-- -----------------------------------------------------------------------------
-- The assignment defines a conversion as "a payment, purchase, registration, or
-- any other meaningful completion event". Two levels are measured:
--   conversion (primary)  a completed order: the brand's order-confirmation page
--   conversion (broad)    an order, an account registration, or a financing application
--                         (Affirm / Klarna / … for one of the brands' carts)
-- Cart and checkout reach are kept as funnel steps: on a single day, completed
-- mattress orders are too few to compare brands on their own.
--
-- Order-confirmation patterns, checked against the URLs present in the data:
--   Walmart     walmart.com/thankyou
--   Shopify     /checkouts/…/thank-you (also fired by the checkout's web-pixel iframe)
--   Magento     /checkout/onepage/success
--   generic     /thank-you, /order-confirmation, /checkout/confirmation …
-- Any brand subdomain counts (e.g. checkout.helixsleep.com). Patterns are matched
-- on the URL path only, so a "/thankyou" inside a query string does not count.
--
-- Attribution: last click, within the same day (the data covers one day). A click
-- converts if the same user reaches the step after it and before any later
-- affiliate click to that brand.
-- =============================================================================

CREATE OR REPLACE MACRO url_path(u) AS
    regexp_extract(u, '^[a-z]+://[^/?#]+([^?#]*)', 1);

CREATE OR REPLACE MACRO conversion_re() AS
    '(?i)/(thank[-_]?you|thankyou|checkout/onepage/success|checkout/success|checkout/confirmation|order[-_]?confirmation|order[-_]?complete|purchase/confirmation)(/|\?|#|$)';

CREATE OR REPLACE MACRO cart_re() AS
    '(?i)/(cart|basket)(/|$)';

CREATE OR REPLACE MACRO checkout_re() AS            -- any cart or checkout page
    '(?i)/(cart|basket|checkout|checkouts)(/|\?|#|$)';

CREATE OR REPLACE MACRO registration_re() AS
    '(?i)/(account/(create|signup|sign-up|register)|register|sign-?up|create-?account)(/|$)';

CREATE OR REPLACE MACRO financing_host_re() AS
    '(^|\.)(affirm|klarna|afterpay|synchrony|mysynchrony|acima|katapult|snapfinance)\.com$';

-- Orders ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE conversion_events AS
SELECT brand, user_id, created_time, host, url
FROM brand_user_events
WHERE brand IS NOT NULL
  AND regexp_matches(url_path(url), conversion_re());

-- One order per user per brand per 30 min. The confirmation page often fires
-- several rows (reloads, iframes).
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

-- Funnel steps and the other completion events -----------------------------------------
CREATE OR REPLACE TABLE funnel_events AS
SELECT *
FROM (
    -- On the brand's own domain
    SELECT brand, user_id, created_time,
           regexp_matches(url_path(url), cart_re())                                        AS is_cart,
           regexp_matches(url_path(url), '(?i)/checkouts?(/|$)')
               AND NOT regexp_matches(url_path(url), cart_re())                            AS is_checkout,
           regexp_matches(url_path(url), registration_re())                                AS is_registration,
           FALSE                                                                           AS is_financing
    FROM brand_user_events
    WHERE brand IS NOT NULL
    UNION ALL
    -- A financing application on the lender's site, for a cart from one of the brands
    SELECT b.brand, e.user_id, e.created_time, FALSE, FALSE, FALSE, TRUE
    FROM brand_user_events e
    JOIN brands b
      ON regexp_matches(lower(coalesce(try(url_decode(e.url)), e.url)), split_part(b.domain, '.', 1))
    WHERE regexp_matches(e.host, financing_host_re())
)
WHERE is_cart OR is_checkout OR is_registration OR is_financing;

-- Click-level outcome ----------------------------------------------------------------
CREATE OR REPLACE TABLE click_outcomes AS
WITH clicks AS (
    SELECT brand, click_key, user_id, click_time,
           lead(click_time) OVER (PARTITION BY brand, user_id ORDER BY click_time) AS next_click_time
    FROM affiliate_clicks
),
funnel AS (
    SELECT c.brand, c.click_key,
           bool_or(f.is_cart)          AS reached_cart,
           bool_or(f.is_checkout)      AS reached_checkout,
           bool_or(f.is_registration)  AS registered,
           bool_or(f.is_financing)     AS applied_financing
    FROM clicks c
    JOIN funnel_events f
      ON f.brand = c.brand AND f.user_id = c.user_id
     AND f.created_time >= c.click_time
     AND (c.next_click_time IS NULL OR f.created_time < c.next_click_time)
    GROUP BY c.brand, c.click_key
)
SELECT c.brand,
       c.click_key,
       min(v.conversion_time)                                   AS conversion_time,
       min(v.conversion_time) IS NOT NULL                       AS converted,
       coalesce(any_value(f.reached_cart), FALSE)               AS reached_cart,
       coalesce(any_value(f.reached_checkout), FALSE)           AS reached_checkout,
       coalesce(any_value(f.registered), FALSE)                 AS registered,
       coalesce(any_value(f.applied_financing), FALSE)          AS applied_financing,
       (min(v.conversion_time) IS NOT NULL
        OR coalesce(any_value(f.registered), FALSE)
        OR coalesce(any_value(f.applied_financing), FALSE))     AS converted_broad
FROM clicks c
LEFT JOIN conversions v
       ON v.brand = c.brand AND v.user_id = c.user_id
      AND v.conversion_time >= c.click_time
      AND (c.next_click_time IS NULL OR v.conversion_time < c.next_click_time)
LEFT JOIN funnel f
       ON f.brand = c.brand AND f.click_key = c.click_key
GROUP BY c.brand, c.click_key;

-- Site funnel by brand, all traffic sources: how visible each step is in the data ------
CREATE OR REPLACE TABLE brand_funnel AS
SELECT b.brand,
       (SELECT count(DISTINCT user_id) FROM brand_user_events e WHERE e.brand = b.brand AND e.is_brand_page) AS visitors,
       count(DISTINCT f.user_id) FILTER (WHERE f.is_cart)          AS reached_cart,
       count(DISTINCT f.user_id) FILTER (WHERE f.is_checkout)      AS reached_checkout,
       count(DISTINCT f.user_id) FILTER (WHERE f.is_registration)  AS registered,
       count(DISTINCT f.user_id) FILTER (WHERE f.is_financing)     AS applied_financing,
       (SELECT count(DISTINCT user_id) FROM conversions o WHERE o.brand = b.brand) AS ordered
FROM brands b
LEFT JOIN funnel_events f ON f.brand = b.brand
GROUP BY b.brand;
