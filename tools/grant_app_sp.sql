-- Least-privilege grants for the Trial Enrollment Risk Cockpit app's service principal (9b18c2bd-5881-454c-9bca-2635a0bef106).
-- The app sees governed VIEWS + the metric view only, never the underlying tables.
GRANT USE CATALOG ON CATALOG km_catalog TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT USE SCHEMA  ON SCHEMA km_catalog.febar_trials TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE km_catalog.febar_trials.v_portfolio_worklist TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE km_catalog.febar_trials.v_enrollment_weekly  TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE km_catalog.febar_trials.mv_portfolio_kpis    TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT EXECUTE ON FUNCTION km_catalog.febar_trials.has_ta_access       TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT EXECUTE ON FUNCTION km_catalog.febar_trials.can_view_financials TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
-- entitlement: the cockpit is used by portfolio leadership -> all therapeutic areas incl. financials
MERGE INTO km_catalog.febar_trials.ta_access t USING (SELECT '9b18c2bd-5881-454c-9bca-2635a0bef106' AS principal, 'ALL' AS therapeutic_area, true AS can_view_financials) s
ON t.principal = s.principal AND t.therapeutic_area = s.therapeutic_area WHEN NOT MATCHED THEN INSERT *;
GRANT SELECT ON TABLE km_catalog.febar_trials.v_study_interventions TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT ON TABLE km_catalog.febar_trials.v_trial_landscape TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT ON TABLE km_catalog.febar_trials.value_assumptions TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
