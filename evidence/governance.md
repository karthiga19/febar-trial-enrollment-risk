# Unity Catalog governance evidence

**Tags on tables (governed `sensitivity` policy + febar_* tags)**
```sql
SELECT table_name, tag_name, tag_value FROM km_catalog.information_schema.table_tags WHERE schema_name = 'febar_trials' ORDER BY 1, 2
```
| table_name | tag_name | tag_value |
|---|---|---|
| bronze_ctgov_studies | febar_layer | bronze |
| bronze_ctgov_studies | febar_source | clinicaltrials_gov_api_v2 |
| bronze_ctgov_studies | sensitivity | public |
| bronze_enrollment_weekly | febar_layer | bronze |
| bronze_enrollment_weekly | febar_source | meridian_edc |
| bronze_enrollment_weekly | sensitivity | internal |
| bronze_portfolio_studies | febar_layer | bronze |
| bronze_portfolio_studies | febar_source | meridian_ctms |
| bronze_portfolio_studies | sensitivity | internal |
| gold_portfolio_status | febar_layer | gold |
| gold_portfolio_status | sensitivity | internal |
| silver_trials | febar_layer | silver |
| silver_trials | febar_source | clinicaltrials_gov_api_v2 |
| silver_trials | sensitivity | public |
| trial_eligibility_ai | febar_derived_by | genai_ai_query |
| trial_eligibility_ai | sensitivity | public |
| trial_risk_worklist | febar_derived_by | ml_and_genai |
| trial_risk_worklist | febar_serving | lakebase_synced |
| trial_risk_worklist | sensitivity | internal |
| trial_stop_reasons | febar_derived_by | genai_ai_query |
| trial_stop_reasons | sensitivity | public |
| value_assumptions | febar_owner_team | clinical_finance |
| value_assumptions | sensitivity | internal |


**Column tags**
```sql
SELECT table_name, column_name, tag_name, tag_value FROM km_catalog.information_schema.column_tags WHERE schema_name = 'febar_trials' ORDER BY 1, 2
```
| column_name | table_name | tag_name | tag_value |
|---|---|---|---|
| delay_cost_usd | trial_risk_worklist | febar_financial | true |
| delay_cost_usd | trial_risk_worklist | sensitivity | internal |
| study_manager | trial_risk_worklist | sensitivity | pii |


**Entitlements table**
```sql
SELECT * FROM km_catalog.febar_trials.ta_access
```
| can_view_financials | principal | therapeutic_area |
|---|---|---|
| true | karthiga.mahali@databricks.com | ALL |
| false | oncology.lead@meridian.example | Oncology |
| true | 9b18c2bd-5881-454c-9bca-2635a0bef106 | ALL |


**App service principal grants (least privilege: views + metric view only)**
```sql
SELECT table_name, privilege_type FROM km_catalog.information_schema.table_privileges WHERE table_schema = 'febar_trials' AND grantee = '9b18c2bd-5881-454c-9bca-2635a0bef106' ORDER BY 1
```
| privilege_type | table_name |
|---|---|
| SELECT | value_assumptions |


## Row- and column-level security, demonstrated

Temporarily scope the current user to **Oncology only, no financials**, query the governed view, then restore full access.

**Full access (ALL, financials)**
```sql
SELECT therapeutic_area, count(*) studies, sum(delay_cost_usd) delay_cost_usd FROM km_catalog.febar_trials.v_portfolio_worklist GROUP BY 1 ORDER BY 1
```
| delay_cost_usd | studies | therapeutic_area |
|---|---|---|
| 9405000.0 | 4 | Cardiometabolic |
| 1.2325E7 | 5 | Immunology |
| 8085000.0 | 3 | Infectious Disease |
| 2000000.0 | 4 | Neuroscience |
| 5.5675E7 | 8 | Oncology |


**Scoped to Oncology, no financials (same query)**
```sql
SELECT therapeutic_area, count(*) studies, sum(delay_cost_usd) delay_cost_usd FROM km_catalog.febar_trials.v_portfolio_worklist GROUP BY 1 ORDER BY 1
```
| delay_cost_usd | studies | therapeutic_area |
|---|---|---|
|  | 8 | Oncology |


**Metric view inherits the same security**
```sql
SELECT `Therapeutic Area`, MEASURE(`Studies`) studies, MEASURE(`Delay Cost USD`) delay_cost FROM km_catalog.febar_trials.mv_portfolio_kpis GROUP BY ALL
```
| Therapeutic Area | delay_cost | studies |
|---|---|---|
| Oncology |  | 8 |


**Restored**
```sql
SELECT * FROM km_catalog.febar_trials.ta_access WHERE principal = 'karthiga.mahali@databricks.com'
```
| can_view_financials | principal | therapeutic_area |
|---|---|---|
| true | karthiga.mahali@databricks.com | ALL |


**Lineage captured by Unity Catalog (system.access.table_lineage)**
```sql
SELECT DISTINCT source_table_name, target_table_name FROM system.access.table_lineage
WHERE target_table_schema = 'febar_trials' AND target_table_catalog = 'km_catalog' AND source_table_name IS NOT NULL AND event_date >= current_date() - 2 ORDER BY 2, 1
```
| source_table_name | target_table_name |
|---|---|
| silver_trials | _elig_todo |
| trial_stop_reasons | _elig_todo |
| gold_portfolio_status | _worklist_stage |
| value_assumptions | _worklist_stage |
| bronze_enrollment_weekly | gold_portfolio_enrollment_weekly |
| silver_portfolio_studies | gold_portfolio_enrollment_weekly |
| gold_portfolio_enrollment_weekly | gold_portfolio_status |
| silver_portfolio_studies | gold_portfolio_status |
| v_portfolio_worklist | mv_portfolio_kpis |
| bronze_portfolio_studies | silver_portfolio_studies |
| bronze_ctgov_studies | silver_trials |
| _elig_todo | trial_eligibility_ai |
| silver_trials | trial_features |
| trial_eligibility_ai | trial_features |
| trial_stop_reasons | trial_features |
| _worklist_stage | trial_risk_worklist |
| gold_portfolio_status | trial_risk_worklist |
| value_assumptions | trial_risk_worklist |
| trial_risk_worklist | trial_risk_worklist_synced |
| silver_trials | trial_stop_reasons |
| gold_portfolio_enrollment_weekly | v_enrollment_weekly |
| trial_risk_worklist | v_portfolio_worklist |
| lb_study_interventions_history | v_study_interventions |
| silver_trials | v_trial_landscape |
| trial_eligibility_ai | v_trial_landscape |
| trial_risk_scores | v_trial_landscape |
| trial_stop_reasons | v_trial_landscape |

