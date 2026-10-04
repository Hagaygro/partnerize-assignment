-- =============================================================================
-- 02 · Data validation
-- -----------------------------------------------------------------------------
-- One pass over the full dataset to check the assumptions the analysis relies on:
-- the period covered, ID uniqueness, nulls, double-recorded events, and the
-- panel size (the denominator used for scaling to the US).
-- =============================================================================

CREATE OR REPLACE TABLE dq_profile AS
SELECT count(*)                                                   AS rows,
       count(DISTINCT event_id)                                   AS distinct_event_ids,
       count(*) - count(DISTINCT (user_id, created_time, url))    AS duplicate_rows,      -- same user, second and URL
       count(DISTINCT user_id)                                    AS users,
       count(DISTINCT session_id)                                 AS sessions,
       min(created_time)                                          AS first_event_utc,
       max(created_time)                                          AS last_event_utc,
       count(DISTINCT created_time::DATE)                         AS days,
       count_if(user_id IS NULL OR session_id IS NULL OR created_time IS NULL
                OR host IS NULL OR url IS NULL)                   AS rows_with_nulls
FROM raw_clicks;

-- Activity by UTC hour: a US panel should peak in US daytime (~13:00-04:00 UTC).
CREATE OR REPLACE TABLE dq_hourly AS
SELECT hour(created_time)       AS utc_hour,
       count(*)                 AS rows,
       count(DISTINCT user_id)  AS users
FROM raw_clicks
GROUP BY 1
ORDER BY 1;
