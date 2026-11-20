# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Score the portfolio → the study team's risk worklist
# MAGIC
# MAGIC Two independent early-warning signals are combined per Meridian study:
# MAGIC
# MAGIC 1. **Design risk (ML).** The UC-registered `accrual_risk_model@champion` scores each study's protocol design + GenAI
# MAGIC    eligibility features. It is expressed as a **percentile against ~25K historical industry trials** ("riskier than 91% of trials").
# MAGIC 2. **Operational risk (Lakeflow gold).** Actual vs planned randomizations, trailing run-rate and **projected LPI delay**.
# MAGIC
# MAGIC Delay is converted to **dollars** with assumptions stored in a governed UC table (`value_assumptions`), so finance can
# MAGIC change them without touching code. A **GenAI study brief** (Claude on the Foundation Model API) turns the numbers into
# MAGIC the recommendation a study manager would write. Output: `trial_risk_worklist`, which is synced to Lakebase for the app.

# COMMAND ----------

# MAGIC %pip install -q lightgbm==4.5.0 "mlflow>=3.1"
# MAGIC %restart_python

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## Value assumptions (governed, editable by finance)

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## Score every trial (historical + recruiting landscape) for percentile context, then the Meridian portfolio

# COMMAND ----------

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

# COMMAND ----------

spark.createDataFrame(port[["study_code","design_risk_score","design_risk_percentile","risk_drivers","top_restrictive_criteria",
                            "n_inclusion","n_exclusion","complexity_score"]]).createOrReplaceTempView("port_design")

# COMMAND ----------

# MAGIC %md ## Combine with operational status → priority tier and $ at risk

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## GenAI study brief (what the study manager would write, in 15 seconds instead of 2 hours)

# COMMAND ----------

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

# COMMAND ----------

display(spark.sql("""SELECT study_code, risk_tier, pct_of_plan, projected_delay_days, format_number(delay_cost_usd,0) AS delay_cost_usd,
  design_risk_percentile, recommended_action, headline, brief FROM trial_risk_worklist
  ORDER BY array_position(array('Critical','High','Watch','On track'), risk_tier), delay_cost_usd DESC"""))

# COMMAND ----------

kpi = spark.sql("""SELECT count(*) studies, count_if(risk_tier IN ('Critical','High')) at_risk_studies,
  sum(projected_delay_days) total_projected_delay_days, sum(delay_cost_usd) total_delay_cost_usd,
  sum(addressable_savings_usd) addressable_savings_usd, count_if(headline IS NULL) briefs_missing FROM trial_risk_worklist""").first().asDict()
print(kpi); assert kpi["briefs_missing"] == 0, "some GenAI briefs failed"
