-- =============================================================================
-- 03 · Brands and the working dataset
-- -----------------------------------------------------------------------------
-- `brands` holds one row per analysed brand.
--
-- `brand_user_events` holds every event of every user who touched at least one
-- brand domain that day. This is about 4% of the raw rows, and all later steps
-- run on it. The whole day is kept, not just the brand pages, because the
-- context before a brand visit is what the attribution and fraud analysis
-- needs: the search, the publisher page, a coupon extension, competitor sites.
--
-- Two kinds of duplicates are removed:
--   1. The same event recorded twice under one user: same second, same URL.
--   2. Mirror IDs. The panel sometimes records one person's browsing under two
--      USER_IDs, one a partial copy of the other: identical URL at the identical
--      second. One affiliate click (one network click id) appears under two
--      user ids, and 14–28% of brand visits are such mirrors. Two user ids that
--      share ≥3 identical (second, URL) events are mapped to one person_id, and
--      all later steps work per person. From here on, `user_id` means person.
--
-- Persons, not sessions: a person has ~2.5 parallel "sessions" per day (one per
-- tab), and one click is often recorded in several of them.
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

-- Affiliate-network redirect hosts: the hop a click passes through on its way to the advertiser.
-- The panel rarely records these, but when it does, the hop is the click itself, even if no
-- landing follows (cookie stuffing). Network admin UIs (app.impact.com, members.cj.com …) and
-- tracking tags (emjcd.com, tags.rd.linksynergy.com) are deliberately excluded.
CREATE OR REPLACE MACRO affiliate_hop_host_re() AS
    '(^|\.)(prf\.hn|sjv\.io|pxf\.io|7eer\.net|evyy\.net|ojrq\.net|xuok\.net|vxf\.io|mlfo\.net|anrdoezrs\.net|jdoqocy\.com|tkqlhce\.com|dpbolvw\.net|kqzyfj\.com|qksrv\.net|awin1\.com|pntra\.com|pntrs\.com|pntrac\.com|gopjn\.com|pjtra\.com|pjatr\.com)$|^(click\.linksynergy\.com|shareasale\.com|avantlink\.com|track\.flexlinkspro\.com|goto\.walmart\.com)$';

-- All events of users who touched a brand: a brand domain (any subdomain), or an affiliate hop
-- pointing at one (vanity host such as saatva.prf.hn, or the brand in the encoded destination).
-- Duplicates of type 1 removed.
CREATE OR REPLACE TABLE brand_user_events_raw AS
WITH tagged AS (
    SELECT r.event_id, r.user_id, r.session_id, r.created_time, r.host, r.url,
           nullif(regexp_extract(r.host,
                  '(?:^|\.)((?:saatva|nectarsleep|helixsleep|dreamcloudsleep|walmart)\.com)$', 1), '')
                  AS brand_domain,
           CASE WHEN regexp_matches(r.host, affiliate_hop_host_re())
                -- the brand's full .com domain must appear in the hop's host or destination:
                -- "walmart" alone also matches walmart.ca and gift-card pages
                THEN nullif(regexp_extract(lower(r.host || ' ' || coalesce(try(url_decode(r.url)), r.url)),
                            '\b(saatva|nectarsleep|helixsleep|dreamcloudsleep|walmart)\.com\b', 1), '') || '.com'
           END    AS hop_brand_domain
    FROM raw_clicks r
),
brand_users AS (
    SELECT DISTINCT user_id
    FROM tagged
    WHERE brand_domain IS NOT NULL OR hop_brand_domain IS NOT NULL
)
SELECT t.*
FROM tagged t
SEMI JOIN brand_users u ON t.user_id = u.user_id
QUALIFY row_number() OVER (PARTITION BY t.user_id, t.created_time, t.url ORDER BY t.event_id) = 1;

-- Mirror IDs → one person_id (the smallest user id of the linked pair).
CREATE OR REPLACE TABLE user_alias AS
WITH linked AS (
    SELECT a.user_id AS user_a, b.user_id AS user_b
    FROM brand_user_events_raw a
    JOIN brand_user_events_raw b
      ON a.created_time = b.created_time AND a.url = b.url AND a.user_id < b.user_id
    GROUP BY a.user_id, b.user_id
    HAVING count(*) >= 3
)
SELECT user_b AS user_id, min(user_a) AS person_id
FROM linked
GROUP BY user_b;

CREATE OR REPLACE TABLE brand_user_events AS
SELECT e.event_id,
       coalesce(a.person_id, e.user_id)                          AS user_id,       -- person
       e.user_id                                                 AS raw_user_id,
       e.session_id,
       e.created_time,
       e.host,
       e.url,
       b.brand,
       -- Main site only (bare domain or www). This excludes iframes and tags
       -- such as sgtm.saatva.com and d.emails.saatva.com.
       coalesce(e.host IN (b.domain, 'www.' || b.domain), FALSE) AS is_brand_page,
       h.brand                                                   AS hop_brand      -- affiliate hop towards this brand
FROM brand_user_events_raw e
LEFT JOIN user_alias a ON a.user_id = e.user_id
LEFT JOIN brands b     ON b.domain = e.brand_domain
LEFT JOIN brands h     ON h.domain = e.hop_brand_domain
-- Mirror copies of one event collapse into one row per person.
QUALIFY row_number() OVER (PARTITION BY coalesce(a.person_id, e.user_id), e.created_time, e.url
                           ORDER BY e.event_id) = 1;
