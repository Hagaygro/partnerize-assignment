-- =============================================================================
-- 05 · Brand site visits and their traffic source
-- -----------------------------------------------------------------------------
-- A visit is a run of one user's pageviews on a brand's main site. A gap of more
-- than 30 minutes starts a new visit (the standard web-analytics rule). Visits
-- are built from brand pageviews only, so the iframes and third-party calls
-- that interleave with them do not split a visit.
--
-- The entry URL's parameters give the visit's source. This is the denominator
-- for "what share of a brand's traffic comes from affiliates".
-- =============================================================================

CREATE OR REPLACE TABLE brand_visits AS
WITH pages AS (
    SELECT brand, user_id, created_time, url,
           date_diff('second', lag(created_time) OVER w, created_time) AS secs_since_prev_page
    FROM brand_user_events
    WHERE is_brand_page
    WINDOW w AS (PARTITION BY brand, user_id ORDER BY created_time)
),
numbered AS (
    SELECT *,
           sum(CASE WHEN secs_since_prev_page IS NULL OR secs_since_prev_page > 1800 THEN 1 ELSE 0 END)
               OVER (PARTITION BY brand, user_id ORDER BY created_time
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)            AS visit_no
    FROM pages
)
SELECT brand,
       user_id,
       visit_no,
       min(created_time)                                       AS visit_start,
       max(created_time)                                       AS visit_end,
       count(*)                                                AS pageviews,
       arg_min(url, (created_time, url))                              AS entry_url,
       -- Affiliate parameters on the entry page, or appearing only after the visit started
       regexp_matches(arg_min(url, (created_time, url)), affiliate_marker_re())          AS affiliate_entry,
       bool_or(regexp_matches(url, affiliate_marker_re()))                        AS affiliate_anywhere
FROM numbered
GROUP BY brand, user_id, visit_no;

-- Entry source, classified from the entry URL's parameters (first match wins).
CREATE OR REPLACE TABLE brand_visit_sources AS
SELECT v.*,
       CASE
           WHEN affiliate_entry                                                                    THEN 'Affiliate'
           WHEN regexp_matches(entry_url, '(?i)[?&](gclid|gad_source|gbraid|wbraid|msclkid|gclsrc)=|[?&]utm_medium=(cpc|ppc|sem|paid_?search)') THEN 'Paid search'
           WHEN regexp_matches(entry_url, '(?i)[?&](fbclid|ttclid|sccid|epik)=|[?&]utm_source=(facebook|fb|instagram|ig|meta|tiktok|pinterest|snapchat)') THEN 'Social (paid/organic)'
           WHEN regexp_matches(entry_url, '(?i)[?&]utm_medium=(e-?mail|newsletter|sms)')           THEN 'Email / SMS'
           WHEN regexp_matches(entry_url, '(?i)[?&]utm_medium=(streaming|ctv|tv|display|video)')   THEN 'Display / TV'
           WHEN regexp_matches(entry_url, '(?i)[?&]utm_')                                          THEN 'Other tagged'
           ELSE 'Untagged (organic / direct / referral)'
       END AS entry_source
FROM brand_visits v;
