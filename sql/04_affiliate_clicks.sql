-- =============================================================================
-- 04 · Affiliate clicks
-- -----------------------------------------------------------------------------
-- Definition: an affiliate click is a landing on a brand's main site whose URL
-- carries an affiliate network's tracking parameters. Networks append these
-- parameters on the redirect, so they are present even when the redirect hop
-- itself is not recorded. For the mattress brands it never is: no prf.hn or
-- sjv.io row precedes their landings.
--
-- Markers observed in the data:
--   Saatva      Partnerize  utm_medium=affiliate, click_id=1100l…  (Partnerize click ref)
--   Nectar      Impact      CIDIMP=…, irgwc=1, utm_medium=AFF
--   DreamCloud  Impact      CIDIMP=…, irgwc=1, utm_medium=AFF
--   Walmart     Impact      veh=aff, wmlspartner=imp_<publisher id>, clickid=…
-- Parameters of the other large networks (CJ, Rakuten, Awin, ShareASale,
-- AvantLink) are included so the same rule applies to every brand.
--
-- One click is recorded on several rows (page reloads, parallel sessions, the
-- URL surviving navigation), so clicks are deduplicated on the network click id.
-- =============================================================================

CREATE OR REPLACE MACRO affiliate_marker_re() AS
    '(?i)[?&](irclickid=|cidimp=|irgwc=1|clickref=|app_clickref=|click_id=\d{4}l|cjevent=|cjdata=|ranmid=|ransiteid=|raneaid=|awc=|sscid=|avad=|veh=aff|wmlspartner=imp_|utm_medium=(affiliate|affiliates|aff)(&|#|$))';

-- Value of a query-string parameter (case-insensitive key), URL-decoded; NULL if absent/empty.
CREATE OR REPLACE MACRO url_param(u, key) AS
    nullif(url_decode(regexp_extract(u, '(?i)[?&]' || key || '=([^&#]*)', 1)), '');

-- Every landing row that carries affiliate parameters --------------------------
CREATE OR REPLACE TABLE affiliate_landings AS
SELECT e.brand,
       e.user_id,
       e.session_id,
       e.created_time,
       e.url,
       coalesce(url_param(e.url, 'irclickid'), url_param(e.url, 'cidimp'),
                url_param(e.url, 'clickid'),   url_param(e.url, 'click_id'),
                url_param(e.url, 'app_clickref'), url_param(e.url, 'clickref'),
                url_param(e.url, 'cjevent'),   url_param(e.url, 'awc'),
                url_param(e.url, 'sscid'),     url_param(e.url, 'avad'))          AS network_click_id,
       CASE
           WHEN regexp_matches(e.url, '(?i)[?&](irclickid|cidimp|irgwc)=|[?&]wmlspartner=imp_') THEN 'Impact'
           WHEN regexp_matches(e.url, '(?i)[?&](app_clickref|clickref)=|[?&]click_id=\d{4}l')   THEN 'Partnerize'
           WHEN regexp_matches(e.url, '(?i)[?&](cjevent|cjdata)=')                              THEN 'CJ'
           WHEN regexp_matches(e.url, '(?i)[?&](ranmid|ransiteid|raneaid)=')                    THEN 'Rakuten'
           WHEN regexp_matches(e.url, '(?i)[?&]awc=')                                           THEN 'Awin'
           WHEN regexp_matches(e.url, '(?i)[?&]sscid=')                                         THEN 'ShareASale'
           WHEN regexp_matches(e.url, '(?i)[?&]avad=')                                          THEN 'AvantLink'
           ELSE 'UTM only'
       END                                                                         AS network,
       -- Publisher: Walmart passes Impact's media-partner id, the others a utm_source name.
       lower(coalesce('impact:' || nullif(regexp_extract(e.url, '(?i)[?&]wmlspartner=imp_(\d+)', 1), ''),
                      url_param(e.url, 'utm_source'),
                      url_param(e.url, 'ransiteid'),
                      'unknown'))                                                  AS publisher,
       coalesce(url_param(e.url, 'utm_sharedid'), url_param(e.url, 'sharedid'))   AS publisher_sub_id,
       url_param(e.url, 'coupon')                                                  AS coupon,
       -- A paid-search click id on an affiliate landing means the publisher bought the ad.
       regexp_matches(e.url, '(?i)[?&](gclid|gad_source|gbraid|wbraid|msclkid)=')  AS has_paid_search_click_id
FROM brand_user_events e
WHERE e.is_brand_page
  AND regexp_matches(e.url, affiliate_marker_re());

-- One row per click ------------------------------------------------------------
CREATE OR REPLACE TABLE affiliate_clicks AS
SELECT brand,
       -- Without a click id (rare), fall back to user + exact landing URL.
       coalesce(network_click_id, user_id || '|' || url)  AS click_key,
       min(created_time)                                   AS click_time,
       arg_min(user_id, created_time)                      AS user_id,
       arg_min(session_id, created_time)                   AS session_id,
       arg_min(url, created_time)                          AS landing_url,
       arg_min(network, created_time)                      AS network,
       arg_min(publisher, created_time)                    AS publisher,
       arg_min(publisher_sub_id, created_time)             AS publisher_sub_id,
       arg_min(coupon, created_time)                       AS coupon,
       bool_or(has_paid_search_click_id)                   AS has_paid_search_click_id,
       count(*)                                            AS landing_rows,
       count(DISTINCT session_id)                          AS sessions_recorded
FROM affiliate_landings
GROUP BY brand, click_key;
