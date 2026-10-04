-- =============================================================================
-- 01 · Raw clickstream view
-- -----------------------------------------------------------------------------
-- Reads the 33 Parquet files in place; nothing is copied. Column names are
-- normalised to lower case, and SUBDOMAIN is lower-cased into `host`.
-- Note: SUBDOMAIN already drops a leading "www." (www.saatva.com -> saatva.com).
-- =============================================================================

CREATE OR REPLACE VIEW raw_clicks AS
SELECT _ID              AS event_id,
       USER_ID          AS user_id,
       SESSION_ID       AS session_id,
       CREATED_TIME     AS created_time,   -- UTC
       lower(SUBDOMAIN) AS host,
       URL              AS url
FROM read_parquet('data/raw/*.parquet');
