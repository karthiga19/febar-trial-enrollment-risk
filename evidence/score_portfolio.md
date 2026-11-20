# 04_score_portfolio (executed, with outputs)

Job run `1076184021196428` · task `score_portfolio` · task run `259461317418701` · result **SUCCESS**

# 04 · Score the portfolio → the study team's risk worklist

Two independent early-warning signals are combined per Meridian study:

1. **Design risk (ML).** The UC-registered `accrual_risk_model@champion` scores each study's protocol design + GenAI
   eligibility features. It is expressed as a **percentile against ~25K historical industry trials** ("riskier than 91% of trials").
2. **Operational risk (Lakeflow gold).** Actual vs planned randomizations, trailing run-rate and **projected LPI delay**.

Delay is converted to **dollars** with assumptions stored in a governed UC table (`value_assumptions`), so finance can
change them without touching code. A **GenAI study brief** (Claude on the Foundation Model API) turns the numbers into
the recommendation a study manager would write. Output: `trial_risk_worklist`, which is synced to Lakebase for the app.

```python
%pip install -q lightgbm==4.5.0 "mlflow>=3.1"
%restart_python
```
```python
dbutils.widgets.text("catalog", "km_catalog")
dbutils.widgets.text("schema", "febar_trials")
dbutils.widgets.text("brief_model", "databricks-claude-sonnet-4-6")
dbutils.widgets.text("negative_sample_pct", "20")
CAT, SCH, BRIEF_MODEL = [dbutils.widgets.get(k) for k in ["catalog", "schema", "brief_model"]]
spark.sql(f"USE {CAT}.{SCH}")
import mlflow, numpy as np, pandas as pd
mlflow.set_registry_uri("databricks-uc")
MODEL_URI = f"models:/{CAT}.{SCH}.accrual_risk_model@champion"
model = mlflow.sklearn.load_model(MODEL_URI)
cols = list(model.named_steps["pre"].feature_names_in_)
print(MODEL_URI, len(cols), "features")
```
**Output:**

```text
models:/km_catalog.febar_trials.accrual_risk_model@champion 29 features
```

## Value assumptions (governed, editable by finance)

```python
spark.sql("""
CREATE TABLE IF NOT EXISTS value_assumptions (assumption STRING, phase STRING, value DOUBLE, unit STRING, source STRING)
COMMENT 'Business assumptions used to convert enrollment delay into dollars. Owned by Clinical Finance; edit here, not in code.'
""")
if spark.table("value_assumptions").count() == 0:
    spark.sql("""INSERT INTO value_assumptions VALUES
      ('direct_cost_per_day','PHASE3',55000,'USD/day','Industry estimate (Tufts CSDD 2024: ~$40K/day avg direct trial cost; Phase 3 higher). Conservative, editable.'),
      ('direct_cost_per_day','PHASE2',25000,'USD/day','Industry estimate; editable.'),
      ('lost_sales_per_day','PHASE3',500000,'USD/day','Upside only: delayed launch of an approved asset (Tufts CSDD 2024 ~$500K/day). Not used in headline ROI.'),
      ('lost_sales_per_day','PHASE2',0,'USD/day','Phase 2 delay does not directly delay launch revenue in this model.'),
      ('weeks_earlier_detection',NULL,12,'weeks','Assumed detection advantage vs quarterly portfolio review.')""")
display(spark.table("value_assumptions"))
```
**Output:**

| assumption | phase | value | unit | source |
|---|---|---|---|---|
| direct_cost_per_day | PHASE3 | 55000.0 | USD/day | Industry estimate (Tufts CSDD 2024: ~$40K/day avg direct trial cost; Phase 3 higher). Conservative, editable. |
| direct_cost_per_day | PHASE2 | 25000.0 | USD/day | Industry estimate; editable. |
| lost_sales_per_day | PHASE3 | 500000.0 | USD/day | Upside only: delayed launch of an approved asset (Tufts CSDD 2024 ~$500K/day). Not used in headline ROI. |
| lost_sales_per_day | PHASE2 | 0.0 | USD/day | Phase 2 delay does not directly delay launch revenue in this model. |
| weeks_earlier_detection | None | 12.0 | weeks | Assumed detection advantage vs quarterly portfolio review. |


## Score every trial (historical + recruiting landscape) for percentile context, then the Meridian portfolio

```python
allf = spark.table("trial_features").toPandas()
num_cols = [c for c in cols if c in allf.columns and allf[c].dtype == object and c not in ("phase","allocation","masking","intervention_model","primary_purpose","first_intervention_type","sex","therapeutic_area")]
allf[num_cols] = allf[num_cols].astype("float64")
allf["design_risk_score"] = model.predict_proba(allf[cols])[:, 1]
# population-weighted percentile (completed trials were case-control sampled in notebook 02)
neg_w = 100.0 / float(dbutils.widgets.get("negative_sample_pct"))
h = allf[(allf.cohort == "historical") & allf.label_low_accrual.notna()].sort_values("design_risk_score")
h_scores, h_cumw = h.design_risk_score.values, np.cumsum(np.where(h.label_low_accrual == 1, 1.0, neg_w))
pctile = lambda p: np.interp(p, h_scores, h_cumw / h_cumw[-1]) * 100
allf["design_risk_percentile"] = pctile(allf.design_risk_score).round(1)
spark.createDataFrame(allf[["nct_id","cohort","therapeutic_area","phase","design_risk_score","design_risk_percentile"]]) \
     .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("trial_risk_scores")
spark.sql("COMMENT ON TABLE trial_risk_scores IS 'accrual_risk_model@champion scores for every trial in trial_features; percentile vs historical industry trials. Includes the industry-wide recruiting landscape.'")

port = spark.sql("""
SELECT p.study_code, p.source_nct_id AS nct_id, p.planned_sites
FROM silver_portfolio_studies p""").toPandas().merge(allf, on="nct_id", how="left")
port["n_sites"] = port["planned_sites"]          # the sponsor's own plan overrides the template's public site count
port["design_risk_score"] = model.predict_proba(port[cols])[:, 1]
port["design_risk_percentile"] = pctile(port.design_risk_score).round(1)

# Per-study explanation: top 3 features pushing risk UP (SHAP)
LABELS = {"n_exclusion":"{v:.0f} exclusion criteria","n_inclusion":"{v:.0f} inclusion criteria","complexity_score":"eligibility complexity {v:.0f}/10",
  "requires_biomarker":"biomarker-selected population","requires_prior_therapy_failure":"requires prior-therapy failure",
  "excludes_prior_therapy":"excludes prior therapies","requires_lab_thresholds":"strict lab thresholds","requires_performance_status":"performance-status cut-off",
  "excludes_common_comorbidities":"excludes common comorbidities","requires_invasive_procedure":"invasive procedure required","requires_washout":"washout period required",
  "narrow_population":"narrow / rare population","n_sites":"{v:.0f} planned sites","n_countries":"{v:.0f} countries","eligibility_chars":"long eligibility text ({v:.0f} chars)",
  "n_arms":"{v:.0f} arms","n_secondary_outcomes":"{v:.0f} secondary endpoints","n_primary_outcomes":"{v:.0f} primary endpoints","max_age_years":"max age {v:.0f}",
  "min_age_years":"min age {v:.0f}","n_collaborators":"{v:.0f} collaborators","n_interventions":"{v:.0f} interventions"}
pre, clf = model.named_steps["pre"], model.named_steps["clf"]
X = pre.transform(port[cols]); X = X.toarray() if hasattr(X, 'toarray') else np.asarray(X); fn = pre.get_feature_names_out()
sv = clf.booster_.predict(X, pred_contrib=True)[:, :-1]     # LightGBM native TreeSHAP (last column = bias)
CAT_SRC = {c: c for c in ["phase","allocation","masking","intervention_model","primary_purpose","first_intervention_type","sex","therapeutic_area"]}
def drivers(i):
    """Top 3 features pushing THIS study's risk up; one-hot features only count if the study actually has that category."""
    out = []
    for j in np.argsort(-sv[i]):
        if sv[i, j] <= 0 or len(out) == 3: break
        f, xv = fn[j], X[i, j]
        if f in LABELS:
            v = port.iloc[i][f]
            if v is None or (isinstance(v, float) and np.isnan(v)): continue
            if f.startswith(("requires_", "excludes_", "narrow_")) and not v: continue
            out.append(LABELS[f].format(v=float(v)))
        else:
            base = next((c for c in CAT_SRC if f.startswith(c + "_")), None)
            if base is None or not xv: continue                      # category not present for this study
            out.append(f"{base.replace('_', ' ')}: {f[len(base) + 1:].replace('_', ' ').lower()}")
    return out
port["risk_drivers"] = [drivers(i) for i in range(len(port))]
display(port[["study_code","therapeutic_area","design_risk_percentile","risk_drivers"]].sort_values("design_risk_percentile", ascending=False))
```
**Output:**

| study_code | therapeutic_area | design_risk_percentile | risk_drivers |
|---|---|---|---|
| MRD-ONC-204 | oncology | 99.7 | ['eligibility complexity 8/10', 'long eligibility text (5742 chars)', '15 inclusion criteria'] |
| MRD-ONC-208 | oncology | 98.4 | ['eligibility complexity 8/10', 'long eligibility text (2819 chars)', 'therapeutic area: oncology'] |
| MRD-ONC-203 | oncology | 97.6 | ['eligibility complexity 8/10', 'long eligibility text (1987 chars)', 'intervention model: sequential'] |
| MRD-ONC-210 | oncology | 97.2 | ['eligibility complexity 8/10', '1 arms', '6 secondary endpoints'] |
| MRD-ONC-307 | oncology | 96.4 | ['eligibility complexity 8/10', 'long eligibility text (1730 chars)', 'therapeutic area: oncology'] |
| MRD-NEU-216 | neuroscience | 96.2 | ['eligibility complexity 8/10', '1 arms', 'intervention model: sequential'] |
| MRD-ONC-315 | oncology | 89.8 | ['eligibility complexity 8/10', '1 secondary endpoints', '2 arms'] |
| MRD-IMM-224 | immunology | 89.7 | ['eligibility complexity 8/10', '1 arms', 'phase: phase2'] |
| MRD-NEU-222 | psychiatry | 88.9 | ['long eligibility text (1313 chars)', '2 arms', 'masking: triple'] |
| MRD-IMM-212 | immunology | 88.6 | ['eligibility complexity 8/10', '30 exclusion criteria', 'intervention model: sequential'] |
| MRD-NEU-214 | neuroscience | 74.1 | ['eligibility complexity 8/10', 'long eligibility text (4899 chars)', 'min age 18'] |
| MRD-NEU-219 | neuroscience | 73.6 | ['eligibility complexity 8/10', '2 arms', 'long eligibility text (2127 chars)'] |
| MRD-IMM-320 | other | 73.0 | ['17 exclusion criteria', '7 secondary endpoints', '2 arms'] |
| MRD-ONC-211 | oncology | 66.2 | ['therapeutic area: oncology', '1 arms', 'long eligibility text (1509 chars)'] |
| MRD-CVM-205 | cardiometabolic | 54.1 | ['long eligibility text (1104 chars)', '2 arms', 'phase: phase2'] |
| MRD-INF-323 | infectious_disease | 52.9 | ['therapeutic area: infectious disease', 'long eligibility text (2877 chars)', '2 arms'] |
| MRD-CVM-309 | other | 49.3 | ['max age 17', 'long eligibility text (1307 chars)', '2 arms'] |
| MRD-IMM-206 | immunology | 36.8 | ['1 arms', 'phase: phase2', 'min age 18'] |
| MRD-IMM-221 | other | 36.0 | ['long eligibility text (1388 chars)', '2 arms', '1 primary endpoints'] |
| MRD-INF-318 | infectious_disease | 22.1 | ['therapeutic area: infectious disease', '1 primary endpoints', '2 arms'] |
| MRD-CVM-301 | cardiometabolic | 21.9 | ['3 interventions', '2 arms', 'min age 18'] |
| MRD-CVM-302 | cardiometabolic | 19.1 | ['eligibility complexity 8/10', '2 arms', 'invasive procedure required'] |
| MRD-ONC-213 | oncology | 9.5 | ['intervention model: sequential', 'therapeutic area: oncology', 'performance-status cut-off'] |
| MRD-INF-217 | cardiometabolic | 9.2 | ['min age 18', 'phase: phase2', '9 inclusion criteria'] |


```python
spark.createDataFrame(port[["study_code","design_risk_score","design_risk_percentile","risk_drivers","top_restrictive_criteria",
                            "n_inclusion","n_exclusion","complexity_score"]]).createOrReplaceTempView("port_design")
```
## Combine with operational status → priority tier and $ at risk

```python
spark.sql("""
CREATE OR REPLACE TEMP VIEW worklist_base AS
SELECT
  g.study_code, g.study_title, g.therapeutic_area, g.phase, g.indication, g.study_manager, g.source_nct_id,
  g.target_enrollment, g.planned_sites, g.active_sites, g.planned_fpi_date, g.planned_lpi_date, g.as_of_week,
  g.randomized_cum, g.planned_cum, g.pct_of_plan, g.pts_per_week_8w, g.projected_lpi_date, g.projected_delay_days,
  d.design_risk_score, d.design_risk_percentile, d.risk_drivers, d.top_restrictive_criteria, d.n_inclusion, d.n_exclusion, d.complexity_score,
  CASE WHEN g.projected_delay_days > 120 OR g.pct_of_plan < 0.60 THEN 'Critical'
       WHEN g.projected_delay_days > 45 OR (d.design_risk_percentile >= 80 AND g.pct_of_plan < 0.90) THEN 'High'
       WHEN d.design_risk_percentile >= 70 OR g.pct_of_plan < 0.95 THEN 'Watch'
       ELSE 'On track' END AS risk_tier,
  -- Clinical-ops playbook (deterministic, auditable): policy decides the lever, GenAI explains it
  CASE WHEN g.projected_delay_days = 0                         THEN 'monitor'
       WHEN g.active_sites < 0.8 * g.planned_sites              THEN 'site_remediation'
       WHEN d.design_risk_percentile >= 70                      THEN 'protocol_amendment'
       WHEN g.active_sites >= 0.9 * g.planned_sites             THEN 'add_sites'
       ELSE 'recruitment_campaign' END AS recommended_action,
  round(g.projected_delay_days * c.value) AS delay_cost_usd,
  round(least(g.projected_delay_days, a.value * 7) * c.value) AS addressable_savings_usd
FROM gold_portfolio_status g
JOIN port_design d USING (study_code)
JOIN value_assumptions c ON c.assumption = 'direct_cost_per_day' AND c.phase = g.phase
JOIN value_assumptions a ON a.assumption = 'weeks_earlier_detection'
""")
display(spark.sql("""SELECT risk_tier, count(*) studies, sum(projected_delay_days) total_delay_days,
                     format_number(sum(delay_cost_usd),0) delay_cost_usd FROM worklist_base GROUP BY 1
                     ORDER BY array_position(array('Critical','High','Watch','On track'), risk_tier)"""))
```
**Output:**

| risk_tier | studies | total_delay_days | delay_cost_usd |
|---|---|---|---|
| Critical | 7 | 2937 | 82,965,000 |
| High | 2 | 144 | 3,600,000 |
| Watch | 10 | 37 | 925,000 |
| On track | 5 | 0 | 0 |


## GenAI study brief (what the study manager would write, in 15 seconds instead of 2 hours)

```python
BRIEF_SCHEMA = """{"type":"json_schema","json_schema":{"name":"brief","strict":true,"schema":{"type":"object","additionalProperties":false,
 "required":["headline","brief","action_rationale"],"properties":{
  "headline":{"type":"string"},"brief":{"type":"string"},"action_rationale":{"type":"string"}}}}}"""
PROMPT = ("You are a clinical operations director writing a portfolio risk brief for a study manager. Be specific and quantitative, "
  "no hedging, no generic advice. Use only the facts given. headline: <= 12 words. brief: 2-3 sentences covering where enrollment stands vs plan, "
  "the projected delay and its cost, and the most likely cause (design_risk_percentile >= 70 and restrictive criteria point to the protocol; "
  "a low design risk with low per-site yield points to site capacity or recruitment). The lever was already chosen by the clinical-ops playbook "
  "(playbook_action). action_rationale: 1 sentence explaining, with the numbers, why playbook_action is the right lever for this study. FACTS: ")
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW worklist_new AS
WITH b AS (
  SELECT *, ai_query('{BRIEF_MODEL}', concat('{PROMPT.replace("'", "\\'")}', to_json(named_struct(
      'study', study_code, 'title', study_title, 'phase', phase, 'therapeutic_area', therapeutic_area,
      'target_enrollment', target_enrollment, 'randomized_to_date', randomized_cum, 'planned_to_date', planned_cum,
      'pct_of_plan', pct_of_plan, 'active_sites', active_sites, 'planned_sites', planned_sites,
      'trailing_8wk_pts_per_week', pts_per_week_8w, 'planned_lpi', planned_lpi_date, 'projected_lpi', projected_lpi_date,
      'projected_delay_days', projected_delay_days, 'delay_cost_usd', delay_cost_usd,
      'design_risk_percentile_vs_historical_industry_trials', design_risk_percentile, 'model_risk_drivers', risk_drivers,
      'most_restrictive_criteria', top_restrictive_criteria, 'risk_tier', risk_tier, 'playbook_action', recommended_action))),
    responseFormat => '{BRIEF_SCHEMA}', failOnError => false) AS resp
  FROM worklist_base
)
,
p AS (SELECT * EXCEPT (resp), from_json(resp.result, 'headline STRING, brief STRING, action_rationale STRING') AS j FROM b)
SELECT * EXCEPT (j), j.headline, j.brief, j.action_rationale, current_timestamp() AS scored_at
FROM p
""")
# Materialize the GenAI briefs once, then MERGE into a *stable* table: the Lakebase synced table reads its
# Change Data Feed, so only changed studies are re-synced (CREATE OR REPLACE would force a full re-snapshot).
spark.sql("CREATE OR REPLACE TABLE _worklist_stage AS SELECT * FROM worklist_new")
if not spark.catalog.tableExists("trial_risk_worklist"):
    spark.sql("""CREATE TABLE trial_risk_worklist
      COMMENT 'Meridian Therapeutics study-team worklist: design risk (ML) + operational enrollment risk + $ at risk + GenAI brief. Synced to Lakebase for the Trial Enrollment Risk Cockpit app.'
      TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
      AS SELECT * FROM _worklist_stage WHERE 1 = 0""")
    spark.sql("ALTER TABLE trial_risk_worklist ALTER COLUMN study_code SET NOT NULL")
    spark.sql("ALTER TABLE trial_risk_worklist ADD CONSTRAINT worklist_pk PRIMARY KEY (study_code)")
m = spark.sql("""MERGE INTO trial_risk_worklist t USING _worklist_stage s ON t.study_code = s.study_code
  WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT * WHEN NOT MATCHED BY SOURCE THEN DELETE""")
display(m)
spark.sql("DROP TABLE IF EXISTS _worklist_stage")
```
**Output:**

| num_affected_rows | num_updated_rows | num_deleted_rows | num_inserted_rows |
|---|---|---|---|
| 24 | 24 | 0 | 0 |


```python
display(spark.sql("""SELECT study_code, risk_tier, pct_of_plan, projected_delay_days, format_number(delay_cost_usd,0) AS delay_cost_usd,
  design_risk_percentile, recommended_action, headline, brief FROM trial_risk_worklist
  ORDER BY array_position(array('Critical','High','Watch','On track'), risk_tier), delay_cost_usd DESC"""))
```
**Output:**

| study_code | risk_tier | pct_of_plan | projected_delay_days | delay_cost_usd | design_risk_percentile | recommended_action | headline | brief |
|---|---|---|---|---|---|---|---|---|
| MRD-CVM-309 | Critical | 0.871 | 171 | 9,405,000 | 49.3 | add_sites | MRD-CVM-309 Enrollment 13% Behind Plan, 171-Day Delay Projected | MRD-CVM-309 has randomized 182 of 300 patients (87.1% of the 209 planned to date) across 16 of 17 active sites, yielding a trailing 8-week rate of 2.13 patients |
| MRD-INF-323 | Critical | 0.555 | 147 | 8,085,000 | 52.9 | recruitment_campaign | MRD-INF-323 Enrollment 45% Behind Plan; 147-Day Delay Projected | MRD-INF-323 has randomized 81 of 374 patients (55.5% of the 146 planned to date) across 57 of 69 active sites, running at 4.88 patients/week against a rate requ |
| MRD-IMM-224 | Critical | 0.59 | 299 | 7,475,000 | 89.7 | protocol_amendment | MRD-IMM-224 SLE Enrollment 41% Behind Plan; Protocol Driving Critical Delay | MRD-IMM-224 has randomized 72 of 168 patients (59% of the 122 planned to date) across 7 active sites, running at 1.38 patients/week against a pace that requires |
| MRD-IMM-212 | Critical | 0.529 | 130 | 3,250,000 | 88.6 | protocol_amendment | MRD-IMM-212 Critical: Protocol Complexity Driving 130-Day LPI Slip | MRD-IMM-212 has randomized 18 of 80 patients (53% of the 34-patient plan-to-date), generating only 0.75 patients/week across 8 fully active sites — a per-site y |
| MRD-ONC-210 | Critical | 0.087 | 730 | 18,250,000 | 97.2 | site_remediation | MRD-ONC-210 Enrollment 91% Behind Plan; Protocol Complexity Driving 2-Year Delay | MRD-ONC-210 has randomized only 2 of 23 planned patients (8.7% of plan) across 5 of 8 active sites, at a trailing 8-week rate of 0.25 patients/week against a ra |
| MRD-ONC-213 | Critical | 0.384 | 730 | 18,250,000 | 9.5 | recruitment_campaign | MRD-ONC-213 Is 2 Years Behind Plan, Costing $18.25M | MRD-ONC-213 has randomized 28 of 80 patients (38.4% of plan) against a target of 73 by this date, with zero patients enrolled in the trailing 8 weeks across 7 o |
| MRD-ONC-204 | Critical | 0.511 | 730 | 18,250,000 | 99.7 | protocol_amendment | MRD-ONC-204 Protocol Complexity Driving 2-Year Critical Enrollment Delay | MRD-ONC-204 has randomized 72 of 197 patients (51.1% of the 141 planned to date) across 7 active sites at a trailing rate of 0.88 patients/week, projecting last |
| MRD-NEU-219 | High | 0.869 | 80 | 2,000,000 | 73.6 | protocol_amendment | MRD-NEU-219 Enrollment 13% Behind Plan; Protocol Amendment Required | MRD-NEU-219 has randomized 126 of 160 patients (87% of plan) against a target of 145 to date across 9 of 10 active sites, running at 1.75 patients/week — insuff |
| MRD-IMM-221 | High | 0.779 | 64 | 1,600,000 | 36.0 | add_sites | MRD-IMM-221 Enrollment 22% Behind Plan; 64-Day Delay Projected | MRD-IMM-221 has randomized 88 of 150 patients (78% of the 113 planned to date), generating only 2.13 patients/site/week across 11 of 12 active sites. At this ra |
| MRD-ONC-211 | Watch | 0.939 | 37 | 925,000 | 66.2 | recruitment_campaign | MRD-ONC-211 Trails Plan by 37 Days; $925K at Risk | MRD-ONC-211 has randomized 260 of 380 patients (93.9% of the planned 277 to date), running 17 patients behind plan with only 33 of 38 sites active and a trailin |
| MRD-NEU-214 | Watch | 1.364 | 0 | 0 | 74.1 | monitor | MRD-NEU-214 ALS Phase 2: On Track, Protocol Complexity Warrants Watch | MRD-NEU-214 has randomized 105 patients against a plan of 77 to date, achieving 136.4% of planned enrollment across 8 of 8 active sites, with a projected LPI of |
| MRD-IMM-320 | Watch | 1.0 | 0 | 0 | 73.0 | monitor | MRD-IMM-320 On Track — Protocol Complexity Warrants Active Watch | MRD-IMM-320 has randomized 125 of 520 patients (24% of total target), exactly matching the planned-to-date figure of 125, with a trailing 8-week rate of 9.13 pa |
| MRD-ONC-208 | Watch | 1.477 | 0 | 0 | 98.4 | monitor | MRD-ONC-208 Ahead of Plan but Protocol Complexity Warrants Close Watch | MRD-ONC-208 has randomized 65 of 100 patients against a plan-to-date of 44, running at 148% of plan with no projected delay and $0 delay cost at current traject |
| MRD-ONC-307 | Watch | 1.636 | 0 | 0 | 96.4 | monitor | MRD-ONC-307 On Track — Protocol Complexity Warrants Active Monitoring | MRD-ONC-307 has randomized 368 of 544 patients (67.6% of target) against a plan of 225, running 63.6% ahead of the enrollment curve with no projected delay and  |
| MRD-NEU-222 | Watch | 1.056 | 0 | 0 | 88.9 | monitor | MRD-NEU-222 On Track, But High Protocol Complexity Warrants Close Watch | MRD-NEU-222 has randomized 75 of 180 patients (42%), running 5.6% ahead of plan (75 vs. 71 expected), with a current trailing rate of 3.88 patients/week across  |
| MRD-ONC-203 | Watch | 1.345 | 0 | 0 | 97.6 | monitor | MRD-ONC-203 On Track; High Protocol Complexity Warrants Active Watch | MRD-ONC-203 has randomized 222 of 235 patients (135% of plan to date), with a current trailing rate of 6.00 patients/week across 23 of 26 planned sites, yieldin |
| MRD-ONC-315 | Watch | 1.456 | 0 | 0 | 89.8 | monitor | MRD-ONC-315 On Track: 300/300 Enrolled, Zero Delay | MRD-ONC-315 has fully enrolled its 300-patient target, reaching 145.6% of the planned-to-date figure with 19 of 20 planned sites active and a trailing 8-week ra |
| MRD-INF-217 | Watch | 0.645 | 0 | 0 | 9.2 | monitor | MRD-INF-217 Enrollment 35% Below Plan; No Delay Projected Yet | MRD-INF-217 has randomized 20 of 160 patients (12.5% of target) against a plan of 31, running at 64.5% of planned pace across all 12 active sites; however, curr |
| MRD-NEU-216 | Watch | 1.429 | 0 | 0 | 96.2 | monitor | MRD-NEU-216 On Track — High Protocol Complexity Warrants Active Watch | MRD-NEU-216 has randomized 80 patients against a plan of 56 to date, achieving 143% of planned enrollment with all 80 target patients already randomized across  |
| MRD-CVM-301 | On track | 1.078 | 0 | 0 | 21.9 | monitor | MRD-CVM-301 On Track — No Intervention Required | MRD-CVM-301 has randomized 523 of 900 patients (58.1%), running 7.8% ahead of the cumulative enrollment plan (485 planned to date) at 12.75 patients/week across |
| MRD-INF-318 | On track | 1.108 | 0 | 0 | 22.1 | monitor | MRD-INF-318 On Track — No Intervention Required | MRD-INF-318 has randomized 205 of 328 patients (62.5%), running 11% ahead of the cumulative enrollment plan (205 vs. 185 planned to date) across 15 of 17 active |
| MRD-IMM-206 | On track | 1.048 | 0 | 0 | 36.8 | monitor | MRD-IMM-206 On Track — No Intervention Required | MRD-IMM-206 has randomized 110 of 390 patients (28.2%), running at 104.8% of plan with 33 of 37 sites active and a trailing 8-week rate of 7.75 patients/week. T |
| MRD-CVM-302 | On track | 1.288 | 0 | 0 | 19.1 | monitor | MRD-CVM-302 On Track — No Delay, Continue Monitoring | MRD-CVM-302 has randomized 255 of 406 patients (62.8%), running 28.8% ahead of the enrollment plan (255 vs. 198 planned to date) across 46 of 51 planned active  |
| MRD-CVM-205 | On track | 1.905 | 0 | 0 | 54.1 | monitor | MRD-CVM-205 On Track: 80/80 Enrolled, No Delay | MRD-CVM-205 has fully enrolled its target of 80 patients against a plan of 42 to date, achieving 190.5% of planned enrollment with a trailing 8-week rate of 2.1 |


```python
kpi = spark.sql("""SELECT count(*) studies, count_if(risk_tier IN ('Critical','High')) at_risk_studies,
  sum(projected_delay_days) total_projected_delay_days, sum(delay_cost_usd) total_delay_cost_usd,
  sum(addressable_savings_usd) addressable_savings_usd, count_if(headline IS NULL) briefs_missing FROM trial_risk_worklist""").first().asDict()
print(kpi); assert kpi["briefs_missing"] == 0, "some GenAI briefs failed"
```
**Output:**

```text
{'studies': 24, 'at_risk_studies': 9, 'total_projected_delay_days': 3118, 'total_delay_cost_usd': 87490000.0, 'addressable_savings_usd': 24265000.0, 'briefs_missing': 0}
```
