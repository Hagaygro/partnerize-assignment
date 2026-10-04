-- =============================================================================
-- 03 · Brands and the working dataset
-- -----------------------------------------------------------------------------
-- `brands` holds one row per analysed brand.
--
-- `brand_user_events` holds every event of every user who touched at least one
-- brand domain that day. This is about 5% of the raw rows, and all later steps
-- run on it. The whole day is kept, not just the brand pages, because the
-- context before a brand visit is what the attribution and fraud analysis
-- needs: the search, the publisher page, a coupon extension, competitor sites.
--
-- Users, not sessions: a user has ~2.3 parallel "sessions" per day (one per
-- tab), and one affiliate click is often recorded in several of them.
-- =============================================================================

CREATE OR REPLACE TABLE brands AS
SELECT *
FROM (VALUES
    -- brand        domain                 client  brand term in a search query
    ('Saatva',     'saatva.com',          TRUE ,  'saatva'),
    ('Nectar',     'nectarsleep.com',     FALSE,  'nectar'),
    ('Helix',      'helixsleep.com',      FALSE,  'helix'),
    ('DreamCloud', 'dreamcloudsleep.com', FALSE,  'dream ?cloud'),
    ('Walmart',    'walmart.com',         FALSE,  'walmart')
) AS t(brand, domain, is_client, search_term_re);

CREATE OR REPLACE TABLE brand_user_events AS
WITH tagged AS (
    -- Which brand domain (if any) each event is on; any subdomain counts here.
    SELECT r.event_id, r.user_id, r.session_id, r.created_time, r.host, r.url,
           nullif(regexp_extract(r.host,
                  '(?:^|\.)((?:saatva|nectarsleep|helixsleep|dreamcloudsleep|walmart)\.com)$', 1), '')
                  AS brand_domain
    FROM raw_clicks r
),
brand_users AS (
    SELECT DISTINCT user_id
    FROM tagged
    WHERE brand_domain IS NOT NULL
)
SELECT t.event_id,
       t.user_id,
       t.session_id,
       t.created_time,
       t.host,
       t.url,
       b.brand,
       -- Main site only (bare domain or www). This excludes iframes and tags
       -- such as sgtm.saatva.com and d.emails.saatva.com.
       coalesce(t.host IN (b.domain, 'www.' || b.domain), FALSE) AS is_brand_page
FROM tagged t
SEMI JOIN brand_users u ON t.user_id = u.user_id
LEFT JOIN brands b      ON t.brand_domain = b.domain
-- Drop events recorded twice: same user, same second, same URL.
QUALIFY row_number() OVER (PARTITION BY t.user_id, t.created_time, t.url ORDER BY t.event_id) = 1;
