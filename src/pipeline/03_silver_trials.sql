-- SILVER: one clean, typed row per trial (latest version wins), with data-quality expectations.
CREATE OR REFRESH MATERIALIZED VIEW silver_trials (
  CONSTRAINT valid_nct_id      EXPECT (nct_id RLIKE '^NCT[0-9]{8}$') ON VIOLATION DROP ROW,
  CONSTRAINT has_phase         EXPECT (phase IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT has_start_date    EXPECT (start_date IS NOT NULL),
  CONSTRAINT has_eligibility   EXPECT (length(eligibility_criteria) > 50),
  CONSTRAINT sane_enrollment   EXPECT (enrollment_count IS NULL OR enrollment_count BETWEEN 0 AND 1000000)
)
COMMENT 'Curated interventional Phase 2/3 trials from ClinicalTrials.gov: design, sponsor, sites, eligibility text, outcome status'
TBLPROPERTIES ('quality' = 'silver', 'delta.enableChangeDataFeed' = 'true')
AS
WITH latest AS (
  SELECT * FROM bronze_ctgov_studies
  QUALIFY row_number() OVER (PARTITION BY nct_id ORDER BY
    raw:protocolSection.statusModule.lastUpdatePostDateStruct.date::string DESC, source_file_ts DESC) = 1
),
p AS (SELECT nct_id, cohort, raw:protocolSection AS ps FROM latest)
SELECT
  nct_id,
  cohort,
  ps:identificationModule.briefTitle::string                         AS brief_title,
  ps:sponsorCollaboratorsModule.leadSponsor.name::string             AS lead_sponsor,
  ps:sponsorCollaboratorsModule.leadSponsor.class::string            AS sponsor_class,
  ps:statusModule.overallStatus::string                              AS overall_status,
  ps:statusModule.whyStopped::string                                 AS why_stopped,
  CASE WHEN array_contains(cast(ps:designModule.phases AS ARRAY<STRING>), 'PHASE3')
        AND array_contains(cast(ps:designModule.phases AS ARRAY<STRING>), 'PHASE2') THEN 'PHASE2/3'
       WHEN array_contains(cast(ps:designModule.phases AS ARRAY<STRING>), 'PHASE3') THEN 'PHASE3'
       WHEN array_contains(cast(ps:designModule.phases AS ARRAY<STRING>), 'PHASE2') THEN 'PHASE2' END AS phase,
  ps:designModule.designInfo.allocation::string                      AS allocation,
  ps:designModule.designInfo.interventionModel::string               AS intervention_model,
  ps:designModule.designInfo.primaryPurpose::string                  AS primary_purpose,
  ps:designModule.designInfo.maskingInfo.masking::string             AS masking,
  ps:designModule.enrollmentInfo.count::int                          AS enrollment_count,
  ps:designModule.enrollmentInfo.type::string                        AS enrollment_type,
  to_date(rpad(ps:statusModule.startDateStruct.date::string, 10, '-01'))              AS start_date,
  to_date(rpad(ps:statusModule.primaryCompletionDateStruct.date::string, 10, '-01'))  AS primary_completion_date,
  coalesce(array_size(cast(ps:armsInterventionsModule.armGroups AS ARRAY<VARIANT>)), 0)     AS n_arms,
  coalesce(array_size(cast(ps:armsInterventionsModule.interventions AS ARRAY<VARIANT>)), 0) AS n_interventions,
  cast(ps:armsInterventionsModule.interventions[0].type AS STRING)  AS first_intervention_type,
  coalesce(array_size(cast(ps:outcomesModule.primaryOutcomes AS ARRAY<VARIANT>)), 0)   AS n_primary_outcomes,
  coalesce(array_size(cast(ps:outcomesModule.secondaryOutcomes AS ARRAY<VARIANT>)), 0) AS n_secondary_outcomes,
  coalesce(array_size(cast(ps:sponsorCollaboratorsModule.collaborators AS ARRAY<VARIANT>)), 0) AS n_collaborators,
  coalesce(array_size(cast(ps:contactsLocationsModule.locations AS ARRAY<VARIANT>)), 0) AS n_sites,
  coalesce(array_size(array_distinct(transform(cast(ps:contactsLocationsModule.locations AS ARRAY<VARIANT>),
      l -> l:country::string))), 0)                                  AS n_countries,
  array_join(slice(cast(ps:conditionsModule.conditions AS ARRAY<STRING>), 1, 5), '; ') AS conditions,
  ps:eligibilityModule.healthyVolunteers::boolean                    AS healthy_volunteers,
  ps:eligibilityModule.sex::string                                   AS sex,
  ps:eligibilityModule.minimumAge::string                            AS minimum_age,
  ps:eligibilityModule.maximumAge::string                            AS maximum_age,
  ps:eligibilityModule.eligibilityCriteria::string                   AS eligibility_criteria,
  length(ps:eligibilityModule.eligibilityCriteria::string)           AS eligibility_chars
FROM p;
