-- @param study_code STRING
-- Weekly cumulative randomizations: actual vs plan for one study
SELECT week_ending, randomized_cum AS actual, planned_cum AS plan
FROM km_catalog.febar_trials.v_enrollment_weekly
WHERE study_code = :study_code
ORDER BY week_ending
