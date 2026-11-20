-- 05 · Unity Catalog governance + semantic layer (runs as the last job task; idempotent)
USE CATALOG km_catalog;
USE SCHEMA febar_trials;

-- ── 1. Classification tags (values constrained by the workspace's governed tag policies) ──────────
-- sensitivity: public = public ClinicalTrials.gov data, internal = confidential sponsor data, pii = person names
ALTER SCHEMA febar_trials SET TAGS ('febar_domain' = 'clinical_operations');
ALTER TABLE bronze_ctgov_studies       SET TAGS ('sensitivity' = 'public',   'febar_source' = 'clinicaltrials_gov_api_v2', 'febar_layer' = 'bronze');
ALTER TABLE silver_trials              SET TAGS ('sensitivity' = 'public',   'febar_source' = 'clinicaltrials_gov_api_v2', 'febar_layer' = 'silver');
ALTER TABLE bronze_portfolio_studies   SET TAGS ('sensitivity' = 'internal', 'febar_source' = 'meridian_ctms', 'febar_layer' = 'bronze');
ALTER TABLE bronze_enrollment_weekly   SET TAGS ('sensitivity' = 'internal', 'febar_source' = 'meridian_edc',  'febar_layer' = 'bronze');
ALTER TABLE gold_portfolio_status      SET TAGS ('sensitivity' = 'internal', 'febar_layer' = 'gold');
ALTER TABLE trial_stop_reasons         SET TAGS ('sensitivity' = 'public',   'febar_derived_by' = 'genai_ai_query');
ALTER TABLE trial_eligibility_ai       SET TAGS ('sensitivity' = 'public',   'febar_derived_by' = 'genai_ai_query');
ALTER TABLE trial_risk_worklist        SET TAGS ('sensitivity' = 'internal', 'febar_derived_by' = 'ml_and_genai', 'febar_serving' = 'lakebase_synced');
ALTER TABLE value_assumptions          SET TAGS ('sensitivity' = 'internal', 'febar_owner_team' = 'clinical_finance');
ALTER TABLE trial_risk_worklist ALTER COLUMN study_manager  SET TAGS ('sensitivity' = 'pii');
ALTER TABLE trial_risk_worklist ALTER COLUMN delay_cost_usd SET TAGS ('sensitivity' = 'internal', 'febar_financial' = 'true');

-- ── 2. Entitlements: which therapeutic areas each principal may see, and who sees $ ───────────────
CREATE TABLE IF NOT EXISTS ta_access (
  principal STRING COMMENT 'user email or service-principal application id',
  therapeutic_area STRING COMMENT 'therapeutic area, or ALL',
  can_view_financials BOOLEAN COMMENT 'may see delay cost / savings $')
COMMENT 'Row/column entitlements for the Meridian portfolio. Edited by Clinical Ops governance.';
MERGE INTO ta_access t USING (SELECT * FROM VALUES
    ('karthiga.mahali@databricks.com', 'ALL', true),
    ('oncology.lead@meridian.example', 'Oncology', false)   -- illustrative TA-scoped user
  AS v(principal, therapeutic_area, can_view_financials)) s
ON t.principal = s.principal AND t.therapeutic_area = s.therapeutic_area
WHEN NOT MATCHED THEN INSERT *;

CREATE OR REPLACE FUNCTION has_ta_access(ta STRING) RETURNS BOOLEAN
COMMENT 'TRUE if the current principal is entitled to the therapeutic area (row-level security)'
RETURN EXISTS (SELECT 1 FROM ta_access a WHERE a.principal = current_user() AND a.therapeutic_area IN ('ALL', ta));

CREATE OR REPLACE FUNCTION can_view_financials() RETURNS BOOLEAN
COMMENT 'TRUE if the current principal may see $ figures (column-level security)'
RETURN EXISTS (SELECT 1 FROM ta_access a WHERE a.principal = current_user() AND a.can_view_financials);

-- ── 3. Governed, consumer-facing views (Genie + app + BI read these, never the raw tables) ───────
CREATE OR REPLACE VIEW v_portfolio_worklist
COMMENT 'Meridian study-team worklist with row-level (therapeutic area) and column-level ($) security applied. One row per active study.'
AS SELECT
  study_code, study_title, therapeutic_area, phase, indication, study_manager, source_nct_id,
  target_enrollment, planned_sites, active_sites, planned_fpi_date, planned_lpi_date, as_of_week,
  randomized_cum AS randomized_to_date, planned_cum AS planned_to_date, pct_of_plan, pts_per_week_8w,
  projected_lpi_date, projected_delay_days, design_risk_percentile, risk_drivers, top_restrictive_criteria,
  n_inclusion, n_exclusion, complexity_score, risk_tier, recommended_action, headline, brief, action_rationale,
  CASE WHEN can_view_financials() THEN delay_cost_usd END          AS delay_cost_usd,
  CASE WHEN can_view_financials() THEN addressable_savings_usd END AS addressable_savings_usd,
  scored_at
FROM trial_risk_worklist
WHERE has_ta_access(therapeutic_area);

CREATE OR REPLACE VIEW v_enrollment_weekly
COMMENT 'Weekly cumulative actual vs planned randomizations per Meridian study (row-level security applied)'
AS SELECT study_code, therapeutic_area, phase, week_ending, active_sites, planned_sites, screened, randomized,
          randomized_cum, planned_cum, target_enrollment
FROM gold_portfolio_enrollment_weekly WHERE has_ta_access(therapeutic_area);

CREATE OR REPLACE VIEW v_trial_landscape
COMMENT 'Public ClinicalTrials.gov industry Phase 2/3 trials (historical + currently recruiting) with GenAI eligibility features and model design-risk percentile. Use for benchmarking and competitive landscape questions.'
AS SELECT s.nct_id, s.brief_title, s.lead_sponsor, s.cohort, s.overall_status, s.phase, year(s.start_date) AS start_year,
  s.conditions, e.therapeutic_area, s.n_sites, s.n_countries, e.n_inclusion, e.n_exclusion, e.complexity_score,
  e.requires_biomarker, e.top_restrictive_criteria, r.stop_category, r.why_stopped,
  sc.design_risk_percentile,
  coalesce(r.stop_category = 'low_accrual', false) AS terminated_for_low_accrual
FROM silver_trials s
JOIN trial_eligibility_ai e USING (nct_id)
LEFT JOIN trial_stop_reasons r USING (nct_id)
LEFT JOIN trial_risk_scores sc USING (nct_id);

CREATE OR REPLACE VIEW v_study_interventions
COMMENT 'Current state of interventions logged by study managers in the Trial Enrollment Risk Cockpit app. Source: Lakebase clinops.study_interventions, replicated to UC by Lakehouse Sync (CDC history lb_study_interventions_history).'
AS SELECT intervention_id, study_code, action_type, notes, status, risk_tier_at_log, owner_email, created_at, updated_at
FROM (
  SELECT *, row_number() OVER (PARTITION BY intervention_id ORDER BY _pg_lsn DESC, _sort_by DESC) AS rn
  FROM lb_study_interventions_history
  WHERE _pg_change_type IN ('insert', 'update_postimage', 'delete')
)
WHERE rn = 1 AND _pg_change_type <> 'delete'
  AND study_code IN (SELECT study_code FROM trial_risk_worklist WHERE has_ta_access(therapeutic_area));

-- ── 4. Metric view: one governed definition of the portfolio KPIs (used by Genie and the app) ─────
CREATE OR REPLACE VIEW mv_portfolio_kpis
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: km_catalog.febar_trials.v_portfolio_worklist
  comment: "Governed Meridian portfolio enrollment-risk KPIs. Inherits row/column security from v_portfolio_worklist."
  dimensions:
    - name: Therapeutic Area
      expr: therapeutic_area
    - name: Phase
      expr: phase
    - name: Risk Tier
      expr: risk_tier
      comment: "Critical: >120 days projected delay or <60% of plan. High: >45 days, or top-20% design risk and <90% of plan. Watch: top-30% design risk or <95% of plan."
    - name: Study Manager
      expr: study_manager
    - name: Recommended Action
      expr: recommended_action
    - name: Study Code
      expr: study_code
  measures:
    - name: Studies
      expr: COUNT(1)
    - name: At Risk Studies
      expr: COUNT_IF(risk_tier IN ('Critical', 'High'))
      comment: "Studies in Critical or High risk tier"
    - name: Behind Plan Studies
      expr: COUNT_IF(pct_of_plan < 1)
      comment: "Studies whose randomizations to date are below plan to date"
    - name: Randomized To Date
      expr: SUM(randomized_to_date)
    - name: Planned To Date
      expr: SUM(planned_to_date)
    - name: Enrollment Vs Plan
      expr: SUM(randomized_to_date) / NULLIF(SUM(planned_to_date), 0)
      comment: "Portfolio randomizations to date as a fraction of plan to date"
    - name: Projected Delay Days
      expr: SUM(projected_delay_days)
      comment: "Sum of projected last-patient-in delay vs plan, days (capped at 730 per study)"
    - name: Delay Cost USD
      expr: SUM(delay_cost_usd)
      comment: "Projected direct cost of enrollment delay (days x phase daily cost from value_assumptions)"
    - name: Addressable Savings USD
      expr: SUM(addressable_savings_usd)
      comment: "Delay cost avoidable by acting value_assumptions.weeks_earlier_detection weeks earlier"
    - name: Avg Design Risk Percentile
      expr: AVG(design_risk_percentile)
$$;

-- ── 5. Who can use what (consumers get views + model, never raw sponsor tables) ──────────────────
-- (the app service principal is granted in tools/grant_app_sp.sql once the app exists)

-- ── 6. Consumer grants: re-applied every run because CREATE OR REPLACE VIEW drops existing grants ──
-- App service principal (febar-trial-risk). Views + metric view only, never the underlying tables.
GRANT SELECT  ON TABLE v_portfolio_worklist  TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE v_enrollment_weekly   TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE v_study_interventions TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE v_trial_landscape     TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE mv_portfolio_kpis     TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT SELECT  ON TABLE value_assumptions     TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT EXECUTE ON FUNCTION has_ta_access       TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
GRANT EXECUTE ON FUNCTION can_view_financials TO `9b18c2bd-5881-454c-9bca-2635a0bef106`;
