-- GOLD: Meridian portfolio, weekly actual-vs-plan enrollment per study (the operational early-warning signal).
CREATE OR REFRESH MATERIALIZED VIEW silver_portfolio_studies
COMMENT 'Meridian Therapeutics active study master (latest CTMS extract per study)'
TBLPROPERTIES ('quality' = 'silver')
AS SELECT * EXCEPT (source_file, ingested_at, _rescued_data)
FROM bronze_portfolio_studies
QUALIFY row_number() OVER (PARTITION BY study_code ORDER BY ingested_at DESC, source_file DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW gold_portfolio_enrollment_weekly (
  CONSTRAINT nonneg_randomized EXPECT (randomized_cum >= 0)
)
COMMENT 'Weekly cumulative actual vs planned randomizations per Meridian study; planned curve is linear from planned FPI to planned LPI after a site-activation ramp'
TBLPROPERTIES ('quality' = 'gold')
AS
WITH wk AS (
  SELECT study_code, week_ending,
         sum(patients_screened)   AS screened,
         sum(patients_randomized) AS randomized,
         count_if(site_active)    AS active_sites
  FROM bronze_enrollment_weekly
  GROUP BY study_code, week_ending
)
SELECT
  w.study_code, s.therapeutic_area, s.phase, w.week_ending, w.active_sites, s.planned_sites,
  w.screened, w.randomized,
  sum(w.randomized) OVER (PARTITION BY w.study_code ORDER BY w.week_ending) AS randomized_cum,
  s.target_enrollment,
  -- plan: linear from FPI to LPI
  round(least(s.target_enrollment, greatest(0,
     s.target_enrollment * datediff(w.week_ending, s.planned_fpi_date) / datediff(s.planned_lpi_date, s.planned_fpi_date)))) AS planned_cum
FROM wk w JOIN silver_portfolio_studies s USING (study_code);

CREATE OR REFRESH MATERIALIZED VIEW gold_portfolio_status
COMMENT 'Latest enrollment status per Meridian study: % of plan, current run-rate, and projected last-patient-in (LPI) delay vs plan'
TBLPROPERTIES ('quality' = 'gold', 'delta.enableChangeDataFeed' = 'true')
AS
WITH last AS (
  SELECT * FROM gold_portfolio_enrollment_weekly
  QUALIFY row_number() OVER (PARTITION BY study_code ORDER BY week_ending DESC) = 1
),
rate AS (  -- trailing 8-week randomization run-rate
  SELECT study_code, sum(randomized) / 8.0 AS pts_per_week_8w
  FROM (SELECT *, row_number() OVER (PARTITION BY study_code ORDER BY week_ending DESC) AS rn FROM gold_portfolio_enrollment_weekly)
  WHERE rn <= 8 GROUP BY study_code
)
SELECT
  s.study_code, s.source_nct_id, s.study_title, s.therapeutic_area, s.phase, s.indication, s.study_manager,
  s.target_enrollment, s.planned_sites, l.active_sites,
  s.planned_fpi_date, s.planned_lpi_date, l.week_ending AS as_of_week,
  l.randomized_cum, l.planned_cum,
  round(l.randomized_cum / nullif(l.planned_cum, 0), 3)  AS pct_of_plan,
  round(r.pts_per_week_8w, 2)                            AS pts_per_week_8w,
  -- projected LPI at current run-rate; horizon capped at 2 years past plan (a stalled study is "> 730 days late")
  date_add(s.planned_lpi_date, cast(least(730, greatest(0, datediff(
      date_add(l.week_ending, cast(least(3650, coalesce((s.target_enrollment - l.randomized_cum) / nullif(r.pts_per_week_8w, 0) * 7, 3650)) AS INT)),
      s.planned_lpi_date))) AS INT)) AS projected_lpi_date,
  cast(least(730, greatest(0, datediff(
      date_add(l.week_ending, cast(least(3650, coalesce((s.target_enrollment - l.randomized_cum) / nullif(r.pts_per_week_8w, 0) * 7, 3650)) AS INT)),
      s.planned_lpi_date))) AS INT) AS projected_delay_days,
  l.randomized_cum >= s.target_enrollment AS enrollment_complete
FROM silver_portfolio_studies s
JOIN last l USING (study_code)
LEFT JOIN rate r USING (study_code);
