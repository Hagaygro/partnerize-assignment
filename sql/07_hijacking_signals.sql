-- =============================================================================
-- 07 · Attribution-hijacking indicators
-- -----------------------------------------------------------------------------
-- In a genuine affiliate click, the user reads a publisher's page (a review, a
-- deal, a creator post) and clicks through to the brand. In attribution
-- hijacking, the user was reaching the brand anyway: direct, organic search,
-- paid search, social, or already on the site. Malware, an extension or a
-- forced redirect then inserts the affiliate link, so the publisher earns the
-- commission on a sale it did not drive.
--
-- The clickstream shows what the user did just before each affiliate click, so
-- every click gets these indicators. The first four are strong signals that the
-- publisher took credit for a visit it did not create:
--   no_landing          the network registered a click (and cookie) but the brand's site never
--                       loaded (cookie stuffing; see 04)
--   in_checkout_before  was in the brand's cart/checkout in the 30 min before (coupon-extension pattern)
--   already_on_site     was on the brand's site without an affiliate tag in the 30 min before
--   paid_search_id      landing URL carries a Google/Bing ad click id, so the publisher bought the ad
-- Medium / review signals:
--   brand_search_60s    searched for the brand's name in the 60s before
--   coupon_ext_60s      a coupon / cash-back site or extension fired in the 60s before
--   multi_brand_burst   landings on 2+ other advertisers within ±2 min. This is a review signal
--                       only: a real user opening a listicle's links in tabs looks the same, so it
--                       counts as stuffing only if the user then never engages with those sites
--   no_referrer         no activity at all in the 30 min before (weak: also true for app/email clicks)
-- The 30-minute windows are tested against stricter windows in 10_sensitivity.sql.
-- =============================================================================

CREATE OR REPLACE MACRO serp_host_re() AS
    '(^|\.)(google\.[a-z.]+|bing\.com|search\.yahoo\.com|duckduckgo\.com|search\.brave\.com|ecosia\.org|search\.aol\.com|startpage\.com)$';

CREATE OR REPLACE MACRO coupon_host_re() AS
    '(^|\.)(joinhoney\.com|honey\.io|capitaloneshopping\.com|rakuten\.com|retailmenot\.com|karmanow\.com|coupert\.com|couponbirds\.com|dealspotr\.com|couponcabin\.com|topcashback\.com|befrugal\.com|swagbucks\.com|slickdeals\.net|couponfollow\.com|simplycodes\.com|wethrift\.com|savings\.com)$';

-- Each click with the user's events from 30 min before to 2 min after it ------
CREATE OR REPLACE TABLE click_context AS
WITH clicks AS (
    SELECT c.brand, c.click_key, c.user_id, c.click_time, b.search_term_re
    FROM affiliate_clicks c
    JOIN brands b USING (brand)
),
window_events AS (
    SELECT c.brand, c.click_key, c.search_term_re,
           e.created_time, e.host, e.url, e.brand AS event_brand, e.is_brand_page,
           date_diff('second', e.created_time, c.click_time)                   AS secs_before,   -- > 0: before the click
           e.brand = c.brand AND e.is_brand_page
               AND NOT regexp_matches(e.url, affiliate_marker_re())            AS is_untagged_brand_page,
           e.brand = c.brand AND regexp_matches(url_path(e.url), checkout_re()) AS is_brand_checkout
    FROM clicks c
    JOIN brand_user_events e
      ON e.user_id = c.user_id
     AND e.created_time BETWEEN c.click_time - INTERVAL 30 MINUTE
                            AND c.click_time + INTERVAL 2 MINUTE
)
SELECT brand,
       click_key,
       -- exact timing, so the sensitivity step can tighten the windows
       min(secs_before) FILTER (WHERE secs_before > 0 AND is_untagged_brand_page)        AS secs_since_brand_page,
       min(secs_before) FILTER (WHERE secs_before > 0 AND is_brand_checkout)             AS secs_since_checkout,
       bool_or(secs_before > 0 AND is_untagged_brand_page)                               AS already_on_site,
       bool_or(secs_before > 0 AND is_brand_checkout)                                    AS in_checkout_before,
       bool_or(secs_before BETWEEN 1 AND 60
               AND regexp_matches(host, serp_host_re())
               AND regexp_matches(lower(coalesce(url_param(url, 'q'), url_param(url, 'p'), '')),
                                  search_term_re))                                       AS brand_search_60s,
       count(DISTINCT host) FILTER (WHERE abs(secs_before) <= 120
                                     AND coalesce(event_brand, '') <> brand
                                     AND regexp_matches(url, affiliate_marker_re()))     AS other_advertisers_2m,
       bool_or(secs_before BETWEEN 0 AND 60 AND regexp_matches(host, coupon_host_re()))  AS coupon_ext_60s,
       NOT bool_or(secs_before > 0)                                                      AS no_referrer,
       arg_max(host, (created_time, host)) FILTER (WHERE secs_before > 0)                        AS prev_host,
       min(secs_before)            FILTER (WHERE secs_before > 0)                        AS secs_since_prev
FROM window_events
GROUP BY brand, click_key;

-- Click-level risk: the strongest indicator present ---------------------------
CREATE OR REPLACE TABLE click_risk AS
SELECT c.*,
       c.click_source = 'hop, no landing'                  AS no_landing,
       x.already_on_site, x.in_checkout_before, x.brand_search_60s, x.coupon_ext_60s,
       x.secs_since_brand_page, x.secs_since_checkout,
       x.other_advertisers_2m >= 2                         AS multi_brand_burst,
       x.other_advertisers_2m, x.no_referrer, x.prev_host, x.secs_since_prev,
       CASE
           WHEN c.click_source = 'hop, no landing' THEN '0 Click without landing (stuffing)'
           WHEN x.in_checkout_before         THEN '1 Injected at cart/checkout'
           WHEN x.already_on_site            THEN '2 User already on brand site'
           WHEN c.has_paid_search_click_id   THEN '3 Publisher-bought search ad'
           WHEN x.brand_search_60s           THEN '4 Brand search just before'
           WHEN x.coupon_ext_60s             THEN '5 Coupon/cash-back just before'
           WHEN x.other_advertisers_2m >= 2  THEN '6 Multi-brand burst (review)'
           WHEN x.no_referrer                THEN '7 No visible referrer (weak)'
           ELSE                                   '8 No hijack indicator'
       END                                                  AS primary_signal,
       (c.click_source = 'hop, no landing' OR x.in_checkout_before OR x.already_on_site
        OR c.has_paid_search_click_id)                      AS strong_hijack_signal
FROM affiliate_clicks c
JOIN click_context x USING (brand, click_key);
