-- =============================================================================
-- 08 · From panel counts to US estimates
-- -----------------------------------------------------------------------------
-- The data is a browsing panel, a small sample of internet users. To estimate
-- US totals, the panel counts are multiplied by a scale factor F.
--
-- Method: anchor-site calibration (ratio estimator). Pick a large, stable,
-- US-centric site with a public traffic figure. F is its true daily US visits
-- divided by the panel's daily US visits to it. walmart.com is the anchor: it
-- is in the analysis, it is 95% US, and it is the panel's best-measured retail
-- site (~30k visits per day).
--   F = (Similarweb monthly visits × US share ÷ days in month) ÷ panel US visits
-- Validation: F applied to the mattress sites' panel visits should land near
-- their own Similarweb figures. Cross-check: US internet users ÷ panel US users.
--
-- Assumption: the panel covers the mattress sites at the same rate it covers
-- walmart.com (no device or demographic skew between the two audiences).
-- =============================================================================

-- 1) US panel users. The data has no country field. A user is non-US when ≥20% of
--    their events are on non-US country-code domains. ccTLDs used generically
--    worldwide (.co .io .ai .me .tv .app …) are ignored.
CREATE OR REPLACE TABLE panel_users AS
SELECT user_id,
       count(*)                                                                    AS events,
       count_if(regexp_matches(host,
           '\.(uk|ca|au|de|fr|in|br|mx|jp|es|it|nl|pl|se|tr|ru|ar|cl|pe|za|ph|id|my|sg|nz|ie|pk|ng|kr|vn|th|eg|sa|ae|il|ro|cz|gr|pt|ch|at|be|dk|fi|no|hu|ua|cn|tw|hk|bd|ke|ir)$'))
                                                                                   AS non_us_cctld_events,
       non_us_cctld_events < 0.2 * events                                          AS is_us
FROM raw_clicks
GROUP BY user_id;

-- 2) External benchmarks (public pages, retrieved 2026-10-04; latest month shown = Aug 2026).
CREATE OR REPLACE TABLE external_benchmarks AS
SELECT *
FROM (VALUES
    ('walmart.com',         581.7e6, 0.9519, 'Similarweb (Aug 2026)', 'https://www.similarweb.com/website/walmart.com/'),
    ('saatva.com',            2.3e6, 0.9248, 'Similarweb (Aug 2026)', 'https://www.similarweb.com/website/saatva.com/'),
    ('nectarsleep.com',       5.1e6, 0.9656, 'Similarweb (Aug 2026)', 'https://www.similarweb.com/website/nectarsleep.com/'),
    ('dreamcloudsleep.com',   1.9e6, 0.9679, 'Similarweb (Aug 2026)', 'https://www.similarweb.com/website/dreamcloudsleep.com/'),
    ('helixsleep.com',         NULL, 0.9182, 'Similarweb (Aug 2026), visits not public', 'https://www.similarweb.com/website/helixsleep.com/')
) AS t(domain, monthly_visits, us_share, source, source_url);

CREATE OR REPLACE MACRO us_internet_users() AS 324e6;   -- DataReportal, Digital 2026 (93.1% of population)

-- 3) Scale factors --------------------------------------------------------------
CREATE OR REPLACE TABLE scaling AS
WITH panel AS (
    SELECT count(*) FILTER (WHERE v.brand = 'Walmart') AS walmart_us_visits_panel
    FROM brand_visits v
    JOIN panel_users u USING (user_id)
    WHERE u.is_us
),
anchor AS (
    SELECT monthly_visits * us_share / 31 AS walmart_us_visits_per_day      -- August has 31 days
    FROM external_benchmarks
    WHERE domain = 'walmart.com'
)
SELECT p.walmart_us_visits_panel,
       a.walmart_us_visits_per_day,
       a.walmart_us_visits_per_day / p.walmart_us_visits_panel             AS scale_factor,          -- F (primary)
       (SELECT count_if(is_us) FROM panel_users)                          AS us_panel_users,
       us_internet_users() / (SELECT count_if(is_us) FROM panel_users)     AS scale_factor_population -- cross-check
FROM panel p, anchor a;

-- 4) Validation: scaled panel visits vs Similarweb, per brand site --------------
CREATE OR REPLACE TABLE scaling_validation AS
SELECT b.brand,
       count(v.user_id)                                                   AS panel_us_visits,
       round(count(v.user_id) * any_value(s.scale_factor))                AS est_us_visits_per_day,
       round(any_value(x.monthly_visits * x.us_share / 31))               AS similarweb_us_visits_per_day,
       round(count(v.user_id) * any_value(s.scale_factor)
             / nullif(any_value(x.monthly_visits * x.us_share / 31), 0), 2) AS ratio_est_to_similarweb
FROM brands b
LEFT JOIN brand_visits v       ON v.brand = b.brand
                              AND v.user_id IN (SELECT user_id FROM panel_users WHERE is_us)
LEFT JOIN external_benchmarks x ON x.domain = b.domain
CROSS JOIN scaling s
GROUP BY b.brand;
