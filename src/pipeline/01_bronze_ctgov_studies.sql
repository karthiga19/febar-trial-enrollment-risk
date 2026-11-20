-- BRONZE: raw ClinicalTrials.gov API v2 study records, ingested incrementally with Auto Loader.
-- Each landing file = one API page (NDJSON). We keep the full record as VARIANT so upstream
-- schema drift (CT.gov adds fields regularly) never breaks ingestion.
CREATE OR REFRESH STREAMING TABLE bronze_ctgov_studies
COMMENT 'Raw ClinicalTrials.gov study records (public API v2), one row per study per landing file. Source: https://clinicaltrials.gov/data-api/api'
TBLPROPERTIES ('quality' = 'bronze')
AS SELECT
  raw:protocolSection.identificationModule.nctId::string AS nct_id,
  regexp_extract(_metadata.file_path, '/ctgov/([^/]+)/', 1)  AS cohort,
  raw,
  _metadata.file_path            AS source_file,
  _metadata.file_modification_time AS source_file_ts,
  current_timestamp()            AS ingested_at
FROM STREAM read_files(
  '/Volumes/km_catalog/febar_trials/raw/ctgov/',
  format => 'json',
  singleVariantColumn => 'raw'
);
