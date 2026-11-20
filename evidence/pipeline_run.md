# Lakeflow pipeline evidence

Pipeline `febar-trials-lakeflow-pipeline` (`56976097-4d4a-464d-b9ee-1cb03bca5a4e`), serverless SQL Spark Declarative Pipeline.

## Recent updates

| update_id | state | created | full_refresh |
|---|---|---|---|
| 48361afc-5a2d-484c-81eb-92c4afa0826b | COMPLETED | 2026-11-20 21:12 | False |
| 48eb135a-d8f6-4db4-923e-240228ce7252 | COMPLETED | 2026-11-20 21:06 | False |
| 67e846e2-f787-4439-a8b2-a1753d5f20dc | COMPLETED | 2026-11-20 21:00 | False |
| 0bc2c8f5-537d-4c45-9e6e-7bb1d4f517b3 | COMPLETED | 2026-11-20 20:49 | False |
| 9f11af6e-6573-4910-9895-d81002ec1c27 | COMPLETED | 2026-11-20 20:41 | False |
| d68a663e-072f-4694-a5b4-ccdc84c2ed85 | COMPLETED | 2026-11-20 20:16 | False |


## Flow metrics and data-quality expectations (from the pipeline event log, `event_log()` TVF)

Bronze streaming tables are incremental (Auto Loader): the largest update is the initial load; later updates process only newly landed files.

**event_log flow_progress**
```sql
SELECT origin.flow_name AS flow,
  count(*) AS completed_updates,
  max(details:flow_progress.metrics.num_output_rows::bigint) AS largest_update_rows,
  max_by(details:flow_progress.metrics.num_output_rows::bigint, timestamp) AS latest_update_rows,
  max_by(details:flow_progress.data_quality.dropped_records::bigint, timestamp) AS latest_dropped,
  max_by(details:flow_progress.data_quality.expectations::string, timestamp) AS latest_expectations
FROM event_log('56976097-4d4a-464d-b9ee-1cb03bca5a4e')
WHERE event_type = 'flow_progress' AND details:flow_progress.status::string = 'COMPLETED'
GROUP BY 1 ORDER BY 1
```
| completed_updates | flow | largest_update_rows | latest_dropped | latest_expectations | latest_update_rows |
|---|---|---|---|---|---|
| 9 | km_catalog.febar_trials.bronze_ctgov_studies |  |  |  |  |
| 9 | km_catalog.febar_trials.bronze_enrollment_weekly |  |  |  |  |
| 9 | km_catalog.febar_trials.bronze_portfolio_studies |  |  |  |  |
| 9 | km_catalog.febar_trials.gold_portfolio_enrollment_weekly | 1224 | 0 | [{"name":"nonneg_randomized","dataset":"km_catalog.febar_trials.gold_portfolio_enrollment_weekly","passed_records":1224,"failed_records":0}] | 1224 |
| 9 | km_catalog.febar_trials.gold_portfolio_status | 24 | 0 |  | 24 |
| 9 | km_catalog.febar_trials.silver_portfolio_studies | 24 | 0 |  | 24 |
| 9 | km_catalog.febar_trials.silver_trials | 49677 | 0 | [{"name":"has_start_date","dataset":"km_catalog.febar_trials.silver_trials","passed_records":49677,"failed_records":0},{"name":"valid_nct_id | 49677 |



## Table row counts now

**medallion counts**
```sql
SELECT 'bronze_ctgov_studies' t, count(*) n FROM km_catalog.febar_trials.bronze_ctgov_studies UNION ALL
SELECT 'silver_trials', count(*) FROM km_catalog.febar_trials.silver_trials UNION ALL SELECT 'bronze_portfolio_studies', count(*) FROM km_catalog.febar_trials.bronze_portfolio_studies UNION ALL
SELECT 'bronze_enrollment_weekly', count(*) FROM km_catalog.febar_trials.bronze_enrollment_weekly UNION ALL SELECT 'gold_portfolio_enrollment_weekly', count(*) FROM km_catalog.febar_trials.gold_portfolio_enrollment_weekly UNION ALL
SELECT 'gold_portfolio_status', count(*) FROM km_catalog.febar_trials.gold_portfolio_status
```
| n | t |
|---|---|
| 49677 | silver_trials |
| 49677 | bronze_ctgov_studies |
| 24 | bronze_portfolio_studies |
| 23701 | bronze_enrollment_weekly |
| 1224 | gold_portfolio_enrollment_weekly |
| 24 | gold_portfolio_status |


**silver by cohort/status**
```sql
SELECT cohort, overall_status, sponsor_class = 'INDUSTRY' AS industry, count(*) n FROM km_catalog.febar_trials.silver_trials GROUP BY ALL ORDER BY 1,2,3
```
| cohort | industry | n | overall_status |
|---|---|---|---|
| historical | false | 20042 | COMPLETED |
| historical | true | 19088 | COMPLETED |
| historical | false | 4478 | TERMINATED |
| historical | true | 4069 | TERMINATED |
| recruiting | false | 1340 | RECRUITING |
| recruiting | true | 660 | RECRUITING |


**GenAI stop-reason label distribution (industry vs all)**
```sql
SELECT r.stop_category, count(*) all_sponsors, count_if(s.sponsor_class='INDUSTRY') industry FROM km_catalog.febar_trials.trial_stop_reasons r JOIN km_catalog.febar_trials.silver_trials s USING (nct_id) GROUP BY 1 ORDER BY 2 DESC
```
| all_sponsors | industry | stop_category |
|---|---|---|
| 2790 | 656 | low_accrual |
| 1780 | 1486 | business_or_strategic |
| 1410 | 899 | efficacy_futility |
| 422 | 117 | regulatory_or_site_operations |
| 408 | 200 | safety |
| 364 | 38 | funding |
| 235 | 83 | covid_19 |
| 198 | 45 | drug_supply |
| 179 | 112 | unclear |
| 135 | 57 | other |

