-- BRONZE: Meridian Therapeutics (fictional sponsor) clinical-ops feeds.
-- portfolio  = study master from the CTMS (one file per extract)
-- enrollment = weekly site-level enrollment actuals from EDC/IRT (one file per week)
CREATE OR REFRESH STREAMING TABLE bronze_portfolio_studies
COMMENT 'Synthetic CTMS study-master extracts for the fictional sponsor Meridian Therapeutics'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('/Volumes/km_catalog/febar_trials/raw/meridian/portfolio/', format => 'csv', header => true,
  schemaHints => 'target_enrollment INT, planned_sites INT, planned_fpi_date DATE, planned_lpi_date DATE');

CREATE OR REFRESH STREAMING TABLE bronze_enrollment_weekly
COMMENT 'Synthetic weekly site-level enrollment actuals (EDC/IRT feed) for Meridian Therapeutics studies'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('/Volumes/km_catalog/febar_trials/raw/meridian/enrollment/', format => 'csv', header => true,
  schemaHints => 'week_ending DATE, patients_screened INT, patients_randomized INT, site_active BOOLEAN');
