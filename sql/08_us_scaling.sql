-- =============================================================================
-- 08 · From panel counts to US estimates
-- -----------------------------------------------------------------------------
-- The data is a browsing panel, a small sample of internet users. To estimate
-- US totals, the panel counts are multiplied by a scale factor F.
--
-- Method: calibration on a known site (ratio estimator). For a site with a public
-- traffic figure, F = its true daily US visits ÷ the panel's US visits to it that day:
--   F = (Similarweb monthly visits × US share ÷ days in month) ÷ panel US visits
--
-- The panel does not cover every audience at the same rate. Calibrated on
-- walmart.com, F puts the mattress sites at only 35–50% of their own Similarweb
-- traffic. So each brand is scaled with the factor calibrated on its own audience:
--   F_retail    walmart.com                                → Walmart
--   F_mattress  Saatva + Nectar + DreamCloud pooled        → the four mattress brands
--               (Helix has no public visit figure; pooling ~100 panel visits
--                is far more stable than calibrating each brand on 19–51)
-- The other factor is reported as the alternative estimate. For the mattress
-- brands, F_retail is the conservative low end. The population ratio (US internet
-- users ÷ panel US users) is a cross-check.
--
-- Caveats: Similarweb's latest public month is August (the Labor Day mattress sale
-- season), so F_mattress likely overstates an ordinary May day somewhat. The
-- panel-user count includes mirror IDs.
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

-- Conversion-rate range for mattress e-commerce. It is used only where the panel
-- day has too few orders to measure a rate: zero for every mattress brand.
-- Source: Grips Intelligence retailer pages (us-mattress.com and
-- mattressfirmep.com 0.5–1.0%, mattressfirm.com 2.0–2.5%).
CREATE OR REPLACE MACRO mattress_cr_low()  AS 0.005;
CREATE OR REPLACE MACRO mattress_cr_high() AS 0.02;

-- 3) Scale factors --------------------------------------------------------------
CREATE OR REPLACE TABLE scaling AS
WITH panel AS (
    SELECT b.brand, b.domain, count(*) AS panel_us_visits
    FROM brand_visits v
    JOIN brands b USING (brand)
    WHERE v.user_id IN (SELECT user_id FROM panel_users WHERE is_us)
    GROUP BY b.brand, b.domain
),
bench AS (
    SELECT p.brand, p.panel_us_visits,
           x.monthly_visits * x.us_share / 31 AS sw_us_visits_per_day        -- August has 31 days
    FROM panel p
    JOIN external_benchmarks x USING (domain)
    WHERE x.monthly_visits IS NOT NULL
)
SELECT (SELECT panel_us_visits      FROM bench WHERE brand = 'Walmart')                          AS walmart_us_visits_panel,
       (SELECT sw_us_visits_per_day FROM bench WHERE brand = 'Walmart')                          AS walmart_us_visits_per_day,
       (SELECT sw_us_visits_per_day / panel_us_visits FROM bench WHERE brand = 'Walmart')        AS scale_factor_retail,
       (SELECT sum(panel_us_visits)      FROM bench WHERE brand <> 'Walmart')                    AS mattress_us_visits_panel,
       (SELECT sum(sw_us_visits_per_day) FROM bench WHERE brand <> 'Walmart')                    AS mattress_us_visits_per_day,
       (SELECT sum(sw_us_visits_per_day) / sum(panel_us_visits) FROM bench WHERE brand <> 'Walmart') AS scale_factor_mattress,
       (SELECT count_if(is_us) FROM panel_users)                                                AS us_panel_users,
       us_internet_users() / (SELECT count_if(is_us) FROM panel_users)                          AS scale_factor_population;

-- Which factor each brand uses (primary) and the alternative: for the mattress
-- brands the walmart-calibrated factor (conservative low end), for Walmart the
-- population ratio.
CREATE OR REPLACE TABLE brand_scale AS
SELECT b.brand,
       CASE WHEN b.brand = 'Walmart' THEN s.scale_factor_retail     ELSE s.scale_factor_mattress END AS scale_factor,
       CASE WHEN b.brand = 'Walmart' THEN s.scale_factor_population ELSE s.scale_factor_retail   END AS scale_factor_alt
FROM brands b
CROSS JOIN scaling s;

-- 4) Validation: scaled panel visits ÷ Similarweb visits, per brand and factor -----
-- (F_mattress is calibrated on the pooled mattress brands, so for them the ratios
--  average ~1 by construction; their spread shows how consistent the panel is.)
CREATE OR REPLACE TABLE scaling_validation AS
SELECT b.brand,
       count(v.user_id)                                                          AS panel_us_visits,
       round(any_value(x.monthly_visits * x.us_share / 31))                      AS similarweb_us_visits_per_day,
       round(count(v.user_id) * any_value(s.scale_factor_retail)
             / nullif(any_value(x.monthly_visits * x.us_share / 31), 0), 2)      AS ratio_with_f_retail,
       round(count(v.user_id) * any_value(s.scale_factor_mattress)
             / nullif(any_value(x.monthly_visits * x.us_share / 31), 0), 2)      AS ratio_with_f_mattress
FROM brands b
LEFT JOIN brand_visits v        ON v.brand = b.brand
                               AND v.user_id IN (SELECT user_id FROM panel_users WHERE is_us)
LEFT JOIN external_benchmarks x ON x.domain = b.domain
CROSS JOIN scaling s
GROUP BY b.brand;
