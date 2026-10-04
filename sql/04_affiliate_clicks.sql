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
--
-- Second path: the network redirect hop itself (saatva.prf.hn/click/…,
-- goto.walmart.com/c/…). The panel rarely records hops. A hop followed within
-- 60s by a tagged landing is the same click and is not counted again. Any other
-- hop is a click of its own. A hop with no landing at all registered a click
-- (and cookie) without the user ever seeing the brand's site: the signature of
-- cookie stuffing.
-- =============================================================================

CREATE OR REPLACE MACRO affiliate_marker_re() AS
    '(?i)[?&](irclickid=|cidimp=|irgwc=1|clickref=|app_clickref=|click_id=\d{4}l|cjevent=|cjdata=|ranmid=|ransiteid=|raneaid=|awc=|sscid=|avad=|veh=aff|wmlspartner=imp_|utm_medium=(affiliate|affiliates|aff)(&|#|$))';

-- Value of a query-string parameter (case-insensitive key), URL-decoded; NULL if absent/empty.
-- try(): some URLs carry non-UTF8 escapes (e.g. GBK search terms), which url_decode rejects.
CREATE OR REPLACE MACRO url_param(u, key) AS
    nullif(coalesce(try(url_decode(regexp_extract(u, '(?i)[?&]' || key || '=([^&#]*)', 1))),
                    regexp_extract(u, '(?i)[?&]' || key || '=([^&#]*)', 1)), '');

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

-- One row per tagged-landing click -------------------------------------------------
CREATE OR REPLACE TABLE landing_clicks AS
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

-- Redirect hops towards a brand ----------------------------------------------------
CREATE OR REPLACE TABLE affiliate_hops AS
SELECT e.hop_brand AS brand,
       e.user_id,
       e.session_id,
       e.created_time,
       e.host,
       e.url,
       CASE
           WHEN regexp_matches(e.host, '(^|\.)prf\.hn$')                                           THEN 'Partnerize'
           WHEN regexp_matches(e.host, '(^|\.)(pntra|pntrs|pntrac|gopjn|pjtra|pjatr)\.com$')        THEN 'Pepperjam (Partnerize)'
           WHEN regexp_matches(e.host, '(^|\.)(sjv\.io|pxf\.io|7eer\.net|evyy\.net|ojrq\.net|xuok\.net|vxf\.io|mlfo\.net)$')
                OR e.host = 'goto.walmart.com'                                                      THEN 'Impact'
           WHEN regexp_matches(e.host, '(^|\.)(anrdoezrs\.net|jdoqocy\.com|tkqlhce\.com|dpbolvw\.net|kqzyfj\.com|qksrv\.net)$') THEN 'CJ'
           WHEN e.host = 'click.linksynergy.com'                                                   THEN 'Rakuten'
           WHEN e.host IN ('awin1.com', 'shareasale.com')                                          THEN 'Awin'
           WHEN e.host = 'avantlink.com'                                                           THEN 'AvantLink'
           WHEN e.host = 'track.flexlinkspro.com'                                                  THEN 'FlexOffers'
           ELSE 'Other'
       END                                                                         AS network,
       -- Publisher id as encoded in each network's link format
       coalesce('camref:' || nullif(regexp_extract(e.url, 'camref:([0-9A-Za-z]+)', 1), ''),
                'impact:' || nullif(regexp_extract(e.url, '/c/(\d+)/', 1), ''),
                'cj:'     || nullif(regexp_extract(e.url, 'click-(\d+)-', 1), ''),
                'awin:'   || nullif(regexp_extract(e.url, '(?i)awinaffid=(\d+)', 1), ''),
                'unknown')                                                         AS publisher
FROM brand_user_events e
WHERE e.hop_brand IS NOT NULL;

-- Hops that are not the same click as a tagged landing ------------------------------
CREATE OR REPLACE TABLE hop_clicks AS
WITH classified AS (
    SELECT h.*,
           EXISTS (SELECT 1 FROM landing_clicks c
                   WHERE c.brand = h.brand AND c.user_id = h.user_id
                     AND c.click_time BETWEEN h.created_time AND h.created_time + INTERVAL 60 SECOND) AS has_tagged_landing,
           EXISTS (SELECT 1 FROM brand_user_events e
                   WHERE e.user_id = h.user_id AND e.brand = h.brand AND e.is_brand_page
                     AND e.created_time BETWEEN h.created_time AND h.created_time + INTERVAL 60 SECOND) AS has_any_landing,
           -- several hops of one redirect chain (e.g. ojrq.net → brand.xuok.net) count once
           date_diff('second', lag(h.created_time) OVER (PARTITION BY h.brand, h.user_id ORDER BY h.created_time),
                     h.created_time)                                                                AS secs_since_prev_hop
    FROM affiliate_hops h
)
SELECT brand,
       'hop|' || user_id || '|' || created_time::VARCHAR                                AS click_key,
       created_time                                                                     AS click_time,
       user_id,
       session_id,
       NULL::VARCHAR                                                                    AS landing_url,
       network,
       publisher,
       NULL::VARCHAR                                                                    AS publisher_sub_id,
       NULL::VARCHAR                                                                    AS coupon,
       FALSE                                                                            AS has_paid_search_click_id,
       0                                                                                AS landing_rows,
       1                                                                                AS sessions_recorded,
       CASE WHEN has_any_landing THEN 'hop + untagged landing' ELSE 'hop, no landing' END AS click_source
FROM classified
WHERE NOT has_tagged_landing
  AND (secs_since_prev_hop IS NULL OR secs_since_prev_hop > 10);

-- All affiliate clicks ---------------------------------------------------------------
CREATE OR REPLACE TABLE affiliate_clicks AS
SELECT *, 'tagged landing' AS click_source FROM landing_clicks
UNION ALL BY NAME
SELECT * FROM hop_clicks;
