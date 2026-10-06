-- =============================================================================
-- 14 · Funnels a panel can see and a brand cannot
-- -----------------------------------------------------------------------------
-- A brand's own analytics stop at its own domain. The panel follows the same
-- person across sites, so it shows the whole category journey:
--   category_funnel     US mattress shoppers: research → a brand site → a product
--                       page → cart → checkout → order, across ~20 mattress brands
--   brand_funnel_cat    the same steps per brand
--   cross_shopping      for each of the four brands, how many other mattress
--                       brands its visitors also looked at, and which
--   journey_order       where review / comparison sites sit: before or after the
--                       first brand visit
--   click_funnel_stage  the stage a shopper had already reached on the brand's
--                       site when the affiliate click fired. A genuine referral
--                       starts the visit; a hijacked click lands at the bottom
--                       of the funnel, after the cart.
-- One panel day, ~350 mattress shoppers: read the category funnel as the shape
-- of the journey, not as precise conversion rates.
-- =============================================================================

CREATE OR REPLACE MACRO mattress_brand_re() AS
    '(?:^|\.)(saatva|nectarsleep|helixsleep|dreamcloudsleep|casper|purple|tempurpedic|sleepnumber|mattressfirm|tuftandneedle|avocadogreenmattress|brooklynbedding|zinus|bearmattress|puffy|amerisleep|birchliving|laylasleep|nolahmattress|sealy|serta|sienasleep|novilla)\.com$';

-- Review and comparison sites: dedicated mattress review sites, or a mattress
-- article on a general publisher.
CREATE OR REPLACE MACRO review_host_re() AS
    '(^|\.)(mattressclarity\.com|sleepfoundation\.org|mattressnerd\.com|sleepopolis\.com|top5-mattresses\.com|buyersguide\.org|sleepadvisor\.org|nytimes\.com|tomsguide\.com|goodhousekeeping\.com|cnn\.com|forbes\.com|usatoday\.com)$';

CREATE OR REPLACE MACRO product_path_re() AS
    '^/(ip|products?|mattresses|mattress-bundles|bedding|furniture|bed-frames|bases|pillows)/[^/?#]+';

CREATE OR REPLACE TABLE category_events AS
WITH ev AS (
    SELECT coalesce(a.person_id, r.user_id) AS user_id, r.created_time, r.host, r.url,
           nullif(regexp_extract(r.host, mattress_brand_re(), 1), '') AS mbrand
    FROM raw_clicks r
    LEFT JOIN user_alias a ON a.user_id = r.user_id
    WHERE regexp_matches(r.host, mattress_brand_re()) OR regexp_matches(r.host, review_host_re())
)
SELECT ev.user_id, ev.created_time, ev.host, ev.mbrand,
       ev.mbrand IS NULL AND regexp_matches(lower(ev.url), 'mattress')                 AS is_review,
       ev.mbrand IS NOT NULL AND regexp_matches(url_path(ev.url), product_path_re())   AS is_product,
       ev.mbrand IS NOT NULL AND regexp_matches(url_path(ev.url), cart_re())           AS is_cart,
       ev.mbrand IS NOT NULL AND regexp_matches(url_path(ev.url), '(?i)/checkouts?(/|$)')
           AND NOT regexp_matches(url_path(ev.url), cart_re())                         AS is_checkout,
       ev.mbrand IS NOT NULL AND regexp_matches(url_path(ev.url), conversion_re())     AS is_order
FROM ev
JOIN panel_users p ON p.user_id = ev.user_id AND p.is_us
WHERE ev.mbrand IS NOT NULL OR regexp_matches(lower(ev.url), 'mattress');

CREATE OR REPLACE TABLE category_funnel AS
WITH u AS (
    SELECT user_id,
           bool_or(is_review)           AS review,
           bool_or(mbrand IS NOT NULL)  AS brand_site,
           bool_or(is_product)          AS product,
           bool_or(is_cart OR is_checkout) AS cart,
           bool_or(is_checkout)         AS checkout,
           bool_or(is_order)            AS ordered
    FROM category_events GROUP BY user_id
)
SELECT * FROM (VALUES (1, 'Mattress shoppers (review or brand site)'), (2, 'Read a review / comparison'),
                      (3, 'Visited a mattress brand site'), (4, 'Viewed a product page'),
                      (5, 'Reached cart'), (6, 'Reached checkout'), (7, 'Ordered')) AS s(step, stage)
CROSS JOIN LATERAL (
    SELECT CASE s.step WHEN 1 THEN count(*) WHEN 2 THEN count_if(review) WHEN 3 THEN count_if(brand_site)
                       WHEN 4 THEN count_if(product) WHEN 5 THEN count_if(cart) WHEN 6 THEN count_if(checkout)
                       ELSE count_if(ordered) END AS users
    FROM u
)
ORDER BY step;

CREATE OR REPLACE TABLE brand_funnel_cat AS
SELECT mbrand AS brand,
       count(DISTINCT user_id)                                            AS visitors,
       count(DISTINCT user_id) FILTER (WHERE is_product)                  AS product_page,
       count(DISTINCT user_id) FILTER (WHERE is_cart OR is_checkout)      AS cart,
       count(DISTINCT user_id) FILTER (WHERE is_checkout)                 AS checkout,
       count(DISTINCT user_id) FILTER (WHERE is_order)                    AS ordered
FROM category_events
WHERE mbrand IS NOT NULL
GROUP BY mbrand
ORDER BY visitors DESC;

-- Cross-shopping: for visitors of each analysed brand, the other mattress brands they saw
CREATE OR REPLACE TABLE cross_shopping AS
WITH ub AS (SELECT DISTINCT user_id, mbrand FROM category_events WHERE mbrand IS NOT NULL),
focus AS (SELECT * FROM (VALUES ('saatva', 'Saatva'), ('nectarsleep', 'Nectar'), ('helixsleep', 'Helix'),
                                ('dreamcloudsleep', 'DreamCloud')) AS t(mbrand, brand)),
per_user AS (SELECT user_id, count(*) AS brands_seen FROM ub GROUP BY user_id)
SELECT f.brand,
       count(DISTINCT v.user_id)                                                       AS visitors,
       round(avg(p.brands_seen), 1)                                                    AS avg_brands_seen,
       round(100.0 * count_if(p.brands_seen > 1) / count(*), 0)                        AS pct_saw_another_brand,
       (SELECT string_agg(o.mbrand || ' (' || o.n || ')', ', ' ORDER BY o.n DESC, o.mbrand)
        FROM (SELECT x.mbrand, count(DISTINCT x.user_id) AS n
              FROM ub x JOIN ub y ON y.user_id = x.user_id AND y.mbrand = f.mbrand
              WHERE x.mbrand <> f.mbrand GROUP BY x.mbrand ORDER BY n DESC, x.mbrand LIMIT 5) o) AS top_other_brands
FROM focus f
JOIN ub v ON v.mbrand = f.mbrand
JOIN per_user p ON p.user_id = v.user_id
GROUP BY f.brand, f.mbrand
ORDER BY visitors DESC;

-- Where review sites sit in the journey: before or after the first brand visit
CREATE OR REPLACE TABLE journey_order AS
WITH u AS (
    SELECT user_id,
           min(created_time) FILTER (WHERE mbrand IS NOT NULL) AS first_brand,
           min(created_time) FILTER (WHERE is_review)          AS first_review
    FROM category_events GROUP BY user_id
)
SELECT CASE WHEN first_review IS NULL THEN 'Brand sites only'
            WHEN first_brand IS NULL  THEN 'Review sites only'
            WHEN first_review < first_brand THEN 'Review first, then a brand'
            ELSE 'Brand first, then a review' END AS pattern,
       count(*) AS users
FROM u GROUP BY 1 ORDER BY users DESC;

-- Funnel stage on the brand's site when the affiliate click fired ---------------------------
-- Looks at the 30 min before the click, but only since the user's previous affiliate
-- click for the brand: browsing that a previous click started belongs to that click
-- (creator storefronts fire many clicks in a row, each landing on a product page).
CREATE OR REPLACE TABLE click_stage AS
WITH c AS (
    SELECT *, lag(click_time) OVER (PARTITION BY brand, user_id ORDER BY click_time, click_key) AS prev_click_time
    FROM us_clicks
)
SELECT c.brand, c.click_key, c.converted, c.strong_hijack_signal,
       CASE
           WHEN c.no_landing THEN '0 Never reached the site'
           WHEN bool_or(regexp_matches(url_path(e.url), '(?i)/checkouts?(/|$)')
                        AND NOT regexp_matches(url_path(e.url), cart_re()))       THEN '5 Already at checkout'
           WHEN bool_or(regexp_matches(url_path(e.url), cart_re()))               THEN '4 Already in cart'
           WHEN bool_or(regexp_matches(url_path(e.url), product_path_re()))       THEN '3 Already on a product page'
           WHEN bool_or(e.user_id IS NOT NULL)                                    THEN '2 Already browsing the site'
           ELSE                                                                        '1 Click starts the visit'
       END AS stage_at_click
FROM c
LEFT JOIN brand_user_events e
       ON e.user_id = c.user_id AND e.brand = c.brand AND e.is_brand_page
      AND e.created_time <  c.click_time
      AND e.created_time >= c.click_time - INTERVAL 30 MINUTE
      AND (c.prev_click_time IS NULL OR e.created_time > c.prev_click_time)
GROUP BY c.brand, c.click_key, c.converted, c.strong_hijack_signal, c.no_landing;

CREATE OR REPLACE TABLE click_funnel_stage AS
SELECT brand, stage_at_click,
       count(*)                                                                    AS clicks,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY brand), 1)         AS pct_clicks,
       count_if(converted)                                                         AS orders,
       round(100.0 * count_if(converted) / nullif(sum(count_if(converted)) OVER (PARTITION BY brand), 0), 1)
                                                                                   AS pct_orders,
       round(100.0 * count_if(converted) / count(*), 2)                            AS conversion_pct
FROM click_stage
GROUP BY brand, stage_at_click
ORDER BY brand, stage_at_click;
