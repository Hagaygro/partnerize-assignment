-- =============================================================================
-- 12 · Seasonality check on the scale factors
-- -----------------------------------------------------------------------------
-- The scale factors (08) are calibrated on Similarweb's latest public month,
-- August 2026, while the panel day is 1 May 2026. If a site's traffic on 1 May
-- differs from its August average, the factor is off by the same ratio.
--
-- Similarweb's May figures are paid, so Google Trends is used as a free proxy for
-- the seasonal shape: daily US search interest per brand (scripts/fetch_google_trends.py,
-- external/google_trends_us_daily.csv). Trends scales each series 0-100 on its
-- own, so only ratios within a series are used:
--   seasonal ratio  = mean interest in the week around 1 May (28 Apr – 4 May)
--                     ÷ mean interest in August
--   F (May)         = Σ (Similarweb Aug US visits/day × ratio) ÷ Σ panel US visits
--                     (pooled over Saatva, Nectar, DreamCloud, as in 08; Walmart alone)
-- A week, not the single day, because one day of a small brand's search
-- interest is noisy.
--
-- Caveat: search interest is a proxy. Site traffic in a sale season also comes
-- from paid media, email and affiliates, so its swing can differ from the
-- search swing. The result is reported as a sensitivity, not as the headline.
-- =============================================================================

CREATE OR REPLACE TABLE google_trends AS
SELECT * FROM read_csv('external/google_trends_us_daily.csv', header = TRUE);

CREATE OR REPLACE TABLE seasonal_ratio AS
UNPIVOT (
    SELECT avg(Saatva)     FILTER (WHERE day BETWEEN '2026-04-28' AND '2026-05-04')
               / avg(Saatva)     FILTER (WHERE month(day) = 8)      AS Saatva,
           avg(Nectar)     FILTER (WHERE day BETWEEN '2026-04-28' AND '2026-05-04')
               / avg(Nectar)     FILTER (WHERE month(day) = 8)      AS Nectar,
           avg(Helix)      FILTER (WHERE day BETWEEN '2026-04-28' AND '2026-05-04')
               / avg(Helix)      FILTER (WHERE month(day) = 8)      AS Helix,
           avg(DreamCloud) FILTER (WHERE day BETWEEN '2026-04-28' AND '2026-05-04')
               / avg(DreamCloud) FILTER (WHERE month(day) = 8)      AS DreamCloud,
           avg(Walmart)    FILTER (WHERE day BETWEEN '2026-04-28' AND '2026-05-04')
               / avg(Walmart)    FILTER (WHERE month(day) = 8)      AS Walmart
    FROM google_trends
) ON Saatva, Nectar, Helix, DreamCloud, Walmart INTO NAME brand VALUE ratio;

CREATE OR REPLACE TABLE seasonal_scaling AS
WITH f AS (
    SELECT sum(v.similarweb_us_visits_per_day * r.ratio)
               FILTER (WHERE v.brand IN ('Saatva', 'Nectar', 'DreamCloud'))
             / sum(v.panel_us_visits) FILTER (WHERE v.brand IN ('Saatva', 'Nectar', 'DreamCloud')) AS f_mattress_may,
           sum(v.similarweb_us_visits_per_day * r.ratio) FILTER (WHERE v.brand = 'Walmart')
             / sum(v.panel_us_visits) FILTER (WHERE v.brand = 'Walmart')                             AS f_retail_may
    FROM scaling_validation v
    JOIN seasonal_ratio r USING (brand)
)
SELECT c.brand,
       round(r.ratio, 2)                                                       AS trends_may_vs_aug,
       c.scale_factor                                                          AS scale_factor_aug,
       round(CASE WHEN c.brand = 'Walmart' THEN f.f_retail_may ELSE f.f_mattress_may END)
                                                                               AS scale_factor_may,
       c.panel_affiliate_clicks,
       c.est_us_affiliate_clicks                                               AS est_us_affiliate_clicks_aug,
       round(c.panel_affiliate_clicks
             * CASE WHEN c.brand = 'Walmart' THEN f.f_retail_may ELSE f.f_mattress_may END)
                                                                               AS est_us_affiliate_clicks_may
FROM competitor_summary c
JOIN seasonal_ratio r USING (brand)
CROSS JOIN f
ORDER BY c.brand = 'Walmart', c.brand <> 'Saatva', c.brand;
