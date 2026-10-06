-- =============================================================================
-- 11 · Incrementality of clicks fired at cart/checkout, and commission at risk
-- -----------------------------------------------------------------------------
-- 07 flags affiliate clicks that fire while the buyer is already in the cart or
-- checkout, and those clicks convert at ~13%. The obvious objection: buyers in
-- checkout convert at a high rate anyway. This step tests exactly that. If the
-- click is what made the sale, users who got one should order more often than
-- users at the same funnel stage who did not.
--
-- Design (Walmart, US users; the mattress brands have no cart-stage clicks):
--   anchor     the user's first cart view of the day (before any checkout view),
--              and separately their first checkout view: the stage is fixed
--              BEFORE any click, so it cannot be an outcome of the click
--   excluded   anchors with a Walmart affiliate click in the 30 min before: the
--              affiliate brought that user to the cart (genuine referral)
--   injected   a Walmart affiliate click fires after the anchor, within 60 min
--              and before the order
--   control    no Walmart affiliate click in that window
--   outcome    an order within 120 min after the anchor
-- Expected orders for the injected group = Σ over stages of (injected users ×
-- control conversion rate). Observed ≈ expected means the click added no orders:
-- the publisher was paid for a sale that was happening anyway.
-- Bias: an injected user stayed on the site at least until the click fired, while
-- the control includes users who left right after the anchor. That favours the
-- injected group, so the test leans towards finding a lift, not against it.
-- The 95% interval on the observed/expected ratio is the Poisson interval of the
-- observed count.
-- =============================================================================

CREATE OR REPLACE TABLE checkout_anchors AS
WITH fv AS (
    SELECT f.user_id, f.created_time, f.is_checkout
    FROM funnel_events f
    JOIN panel_users p USING (user_id)
    WHERE f.brand = 'Walmart' AND (f.is_cart OR f.is_checkout) AND p.is_us
),
wc AS (SELECT user_id, click_time FROM us_clicks WHERE brand = 'Walmart'),
anchors AS (
    SELECT user_id, 'checkout' AS stage, min(created_time) AS anchor
    FROM fv WHERE is_checkout GROUP BY user_id
    UNION ALL
    SELECT c.user_id, 'cart', min(c.created_time)
    FROM fv c
    WHERE NOT c.is_checkout
      AND NOT EXISTS (SELECT 1 FROM fv k
                      WHERE k.user_id = c.user_id AND k.is_checkout AND k.created_time <= c.created_time)
    GROUP BY c.user_id
),
with_outcome AS (
    SELECT a.*,
           (SELECT min(conversion_time) FROM conversions v
            WHERE v.brand = 'Walmart' AND v.user_id = a.user_id
              AND v.conversion_time > a.anchor
              AND v.conversion_time <= a.anchor + INTERVAL 120 MINUTE)            AS order_time,
           EXISTS (SELECT 1 FROM wc
                   WHERE wc.user_id = a.user_id
                     AND wc.click_time BETWEEN a.anchor - INTERVAL 30 MINUTE AND a.anchor) AS affiliate_referred
    FROM anchors a
)
SELECT w.*,
       EXISTS (SELECT 1 FROM wc
               WHERE wc.user_id = w.user_id
                 AND wc.click_time > w.anchor
                 AND wc.click_time <= least(coalesce(w.order_time, w.anchor + INTERVAL 60 MINUTE),
                                            w.anchor + INTERVAL 60 MINUTE))       AS injected
FROM with_outcome w;

CREATE OR REPLACE TABLE incrementality AS
SELECT stage,
       CASE WHEN injected THEN 'Affiliate click fired after this point' ELSE 'No affiliate click' END AS grp,
       count(*)                                         AS users,
       count(order_time)                                AS orders,
       round(100.0 * count(order_time) / count(*), 1)   AS order_rate_pct
FROM checkout_anchors
WHERE NOT affiliate_referred
GROUP BY ALL
ORDER BY stage DESC, grp;

CREATE OR REPLACE TABLE incrementality_summary AS
WITH s AS (
    SELECT stage,
           count_if(injected)                                         AS injected_users,
           count_if(injected AND order_time IS NOT NULL)              AS injected_orders,
           count_if(NOT injected AND order_time IS NOT NULL) * 1.0
               / count_if(NOT injected)                               AS control_rate
    FROM checkout_anchors
    WHERE NOT affiliate_referred
    GROUP BY stage
)
SELECT sum(injected_users)                                            AS injected_users,
       sum(injected_orders)                                           AS observed_orders,
       round(sum(injected_users * control_rate), 1)                   AS expected_orders_without_click,
       round(sum(injected_orders) / sum(injected_users * control_rate), 2)                     AS observed_to_expected,
       round(poisson_lo(sum(injected_orders)) / sum(injected_users * control_rate), 2)         AS ratio_lo95,
       round(poisson_hi(sum(injected_orders)) / sum(injected_users * control_rate), 2)         AS ratio_hi95,
       round(100.0 * (sum(injected_orders) - sum(injected_users * control_rate))
             / sum(injected_orders), 0)                               AS pct_orders_incremental
FROM s;

-- Commission at risk ----------------------------------------------------------------
-- What the flagged orders cost in commission. Inputs (public sources, retrieved 2026-10-06):
--   Walmart AOV $100–125 (Grips Intelligence, walmart.com, Mar 2026);
--   Walmart commission 1–4% by category (Walmart affiliate program on Impact)
--   Saatva AOV ~$860 (Grips Intelligence, saatva.com, Jun 2026, $850–875)
--   Saatva commission 3–10% (public program terms: 3% base, 10% for partner programs)
-- Walmart: estimated US affiliate-attributed orders/day (09) × share of those
-- orders from flagged clicks (10: 2-min look-back = low, 30-min = high).
-- Saatva: the panel has no Saatva orders, so the share hijacked cannot be measured.
-- The result is the commission per 10 points of hijacked share, applied to the
-- benchmark order range (84–334 orders/day, 09).
CREATE OR REPLACE TABLE commission_at_risk AS
WITH wm AS (
    SELECT c.est_us_converted_clicks AS orders_per_day,
           (SELECT pct_orders_from_strong FROM hijack_sensitivity
            WHERE brand = 'Walmart' AND look_back = '2 min') / 100.0          AS share_lo,
           (SELECT pct_orders_from_strong FROM hijack_sensitivity
            WHERE brand = 'Walmart' AND look_back = '30 min (base)') / 100.0  AS share_hi,
           (SELECT count_if(in_checkout_before AND converted) * 1.0 / count_if(converted)
            FROM us_clicks WHERE brand = 'Walmart')                           AS share_checkout
    FROM competitor_summary c WHERE brand = 'Walmart'
),
sa AS (
    SELECT est_us_converted_clicks_benchmark_lo AS orders_lo,
           est_us_converted_clicks_benchmark_hi AS orders_hi
    FROM competitor_summary WHERE brand = 'Saatva'
)
SELECT 'Walmart' AS brand,
       'All strong indicators' AS scope,
       round(orders_per_day * share_lo)                    AS orders_per_day_lo,
       round(orders_per_day * share_hi)                    AS orders_per_day_hi,
       round(orders_per_day * share_lo * 100 * 0.01)       AS commission_per_day_lo,
       round(orders_per_day * share_hi * 125 * 0.04)       AS commission_per_day_hi,
       round(orders_per_day * share_lo * 100 * 0.01 * 365 / 1e6, 1) AS commission_per_year_lo_musd,
       round(orders_per_day * share_hi * 125 * 0.04 * 365 / 1e6, 1) AS commission_per_year_hi_musd
FROM wm
UNION ALL
SELECT 'Walmart', 'Injected at cart/checkout (tested in this step)',
       round(orders_per_day * share_checkout), round(orders_per_day * share_checkout),
       round(orders_per_day * share_checkout * 100 * 0.01),
       round(orders_per_day * share_checkout * 125 * 0.04),
       round(orders_per_day * share_checkout * 100 * 0.01 * 365 / 1e6, 1),
       round(orders_per_day * share_checkout * 125 * 0.04 * 365 / 1e6, 1)
FROM wm
UNION ALL
SELECT 'Saatva', 'Per 10% of affiliate orders hijacked',
       round(orders_lo * 0.1), round(orders_hi * 0.1),
       round(orders_lo * 0.1 * 860 * 0.03), round(orders_hi * 0.1 * 860 * 0.10),
       round(orders_lo * 0.1 * 860 * 0.03 * 365 / 1e6, 2),
       round(orders_hi * 0.1 * 860 * 0.10 * 365 / 1e6, 2)
FROM sa;
