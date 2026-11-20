# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Train the low-accrual termination risk model
# MAGIC
# MAGIC **Question the model answers:** *given a trial's design and eligibility criteria, how likely is it to be
# MAGIC terminated because it could not enroll enough patients?*
# MAGIC
# MAGIC * **Population:** industry-sponsored interventional Phase 2/3 trials, started 2010–2022, that either **completed** or were
# MAGIC   **terminated for low accrual** (label from notebook 02's GenAI stop-reason classifier). Trials terminated for other
# MAGIC   reasons (safety, futility, business) are excluded; they are not enrollment failures.
# MAGIC * **Honest evaluation:** an out-of-time split. Train on trials started ≤2017, test on 2018–2022.
# MAGIC * **GenAI lift is measured, not assumed:** we train a *design-only* baseline and a *design + GenAI eligibility features*
# MAGIC   model, and compare them on the same test set.
# MAGIC * **Case-control weighting:** notebook 02 extracted eligibility for *all* low-accrual terminations but only a
# MAGIC   `negative_sample_pct`% sample of completed trials. Each control gets weight `100/negative_sample_pct`, so the metrics and
# MAGIC   base rate below describe the real population, not the sample.
# MAGIC * **Leakage guard:** actual enrollment count, completion dates and status fields are **never** used as features.

# COMMAND ----------

# MAGIC %pip install -q lightgbm==4.5.0 "mlflow>=3.1"
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "km_catalog")
dbutils.widgets.text("schema", "febar_trials")
dbutils.widgets.text("negative_sample_pct", "20")
CAT, SCH = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
NEG_W = 100.0 / float(dbutils.widgets.get("negative_sample_pct"))
spark.sql(f"USE {CAT}.{SCH}")
MODEL_NAME = f"{CAT}.{SCH}.accrual_risk_model"

import mlflow, numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from lightgbm import LGBMClassifier
mlflow.set_registry_uri("databricks-uc")
user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{user}/febar_accrual_risk")

# COMMAND ----------

# MAGIC %md ## Feature table (governed in UC, reused at scoring time)

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE trial_features
COMMENT 'ML feature table: one row per trial = design features (silver_trials) + GenAI eligibility features (trial_eligibility_ai) + label (trial_stop_reasons). Feature logic shared by training and scoring.'
AS
SELECT
  s.nct_id, s.cohort, s.overall_status, year(s.start_date) AS start_year,
  CASE WHEN s.overall_status='COMPLETED' THEN 0
       WHEN r.stop_category='low_accrual' THEN 1 END                      AS label_low_accrual,
  -- design features
  s.phase, coalesce(s.allocation,'NA') allocation, coalesce(s.masking,'NA') masking,
  coalesce(s.intervention_model,'NA') intervention_model, coalesce(s.primary_purpose,'NA') primary_purpose,
  coalesce(s.first_intervention_type,'NA') first_intervention_type,
  s.n_arms, s.n_interventions, s.n_primary_outcomes, s.n_secondary_outcomes, s.n_collaborators,
  s.n_sites, s.n_countries, cast(coalesce(s.healthy_volunteers,false) AS INT) healthy_volunteers, coalesce(s.sex,'ALL') sex,
  cast(try_cast(regexp_extract(s.minimum_age, '([0-9]+)', 1) AS INT) * CASE WHEN s.minimum_age ILIKE '%month%' THEN 1.0/12 ELSE 1 END AS DOUBLE) AS min_age_years,
  cast(try_cast(regexp_extract(s.maximum_age, '([0-9]+)', 1) AS INT) * CASE WHEN s.maximum_age ILIKE '%month%' THEN 1.0/12 ELSE 1 END AS DOUBLE) AS max_age_years,
  s.eligibility_chars,
  -- GenAI eligibility features
  e.therapeutic_area, e.n_inclusion, e.n_exclusion,
  cast(e.requires_biomarker AS INT) requires_biomarker, cast(e.requires_prior_therapy_failure AS INT) requires_prior_therapy_failure,
  cast(e.excludes_prior_therapy AS INT) excludes_prior_therapy, cast(e.requires_lab_thresholds AS INT) requires_lab_thresholds,
  cast(e.requires_performance_status AS INT) requires_performance_status, cast(e.excludes_common_comorbidities AS INT) excludes_common_comorbidities,
  cast(e.requires_invasive_procedure AS INT) requires_invasive_procedure, cast(e.requires_washout AS INT) requires_washout,
  cast(e.narrow_population AS INT) narrow_population, e.complexity_score, e.top_restrictive_criteria
FROM silver_trials s
JOIN trial_eligibility_ai e USING (nct_id)
LEFT JOIN trial_stop_reasons r USING (nct_id)
""")
df = spark.sql("SELECT * FROM trial_features WHERE cohort='historical' AND label_low_accrual IS NOT NULL").toPandas()
df["w"] = np.where(df.label_low_accrual == 1, 1.0, NEG_W)
print(df.shape); print(df.groupby("label_low_accrual").agg(rows=("w", "size"), population_weight=("w", "sum")))
print(f"population low-accrual termination rate ≈ {np.average(df.label_low_accrual, weights=df.w):.3%}")

# COMMAND ----------

CAT_COLS_DESIGN = ["phase","allocation","masking","intervention_model","primary_purpose","first_intervention_type","sex"]
# n_sites / n_countries are deliberately EXCLUDED from the champion: on CT.gov, terminated trials often list fewer
# sites (sites never activated are dropped from the record), so site counts partly encode the outcome (leakage).
# They are kept only in a separate "leakage_check" run below so the effect is visible.
NUM_COLS_DESIGN = ["n_arms","n_interventions","n_primary_outcomes","n_secondary_outcomes","n_collaborators",
                   "healthy_volunteers","min_age_years","max_age_years","eligibility_chars"]
SITE_COLS = ["n_sites","n_countries"]
CAT_COLS_AI = ["therapeutic_area"]
NUM_COLS_AI = ["n_inclusion","n_exclusion","requires_biomarker","requires_prior_therapy_failure","excludes_prior_therapy",
               "requires_lab_thresholds","requires_performance_status","excludes_common_comorbidities",
               "requires_invasive_procedure","requires_washout","narrow_population","complexity_score"]

df[NUM_COLS_DESIGN + NUM_COLS_AI + SITE_COLS] = df[NUM_COLS_DESIGN + NUM_COLS_AI + SITE_COLS].astype("float64")
train, test = df[df.start_year <= 2017], df[df.start_year >= 2018]
wrate = lambda d: np.average(d.label_low_accrual, weights=d.w)
print(f"train {len(train):,} rows (weighted pos rate {wrate(train):.3f}) | test {len(test):,} rows (weighted pos rate {wrate(test):.3f})")

def make_pipe(cat_cols, num_cols):
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), cat_cols),
                             ("num", "passthrough", num_cols)], verbose_feature_names_out=False)
    clf = LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=40,
                         subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                         scale_pos_weight=(1 - wrate(train)) / wrate(train),
                         random_state=7, verbose=-1)
    return Pipeline([("pre", pre), ("clf", clf)])

def evaluate(pipe, X, y, w):
    """Population-weighted metrics (undo case-control sampling)."""
    p = pipe.predict_proba(X)[:, 1]
    order = np.argsort(-p); cw = np.cumsum(w.values[order])
    top = order[cw <= 0.10 * cw[-1]]                        # top 10% of the *population* by predicted risk
    base = np.average(y, weights=w)
    top_prec = np.average(y.values[top], weights=w.values[top])
    return {"roc_auc": roc_auc_score(y, p, sample_weight=w), "pr_auc": average_precision_score(y, p, sample_weight=w),
            "top_decile_precision": top_prec, "top_decile_lift": top_prec / base,
            "top_decile_capture": (y.values[top] * w.values[top]).sum() / (y.values * w.values).sum(),
            "brier": brier_score_loss(y, p, sample_weight=w), "base_rate": base}, p

# COMMAND ----------

results = {}
for name, cats, nums in [("design_only", CAT_COLS_DESIGN, NUM_COLS_DESIGN),
                         ("design_plus_genai", CAT_COLS_DESIGN + CAT_COLS_AI, NUM_COLS_DESIGN + NUM_COLS_AI),
                         ("leakage_check_with_site_counts", CAT_COLS_DESIGN + CAT_COLS_AI, NUM_COLS_DESIGN + NUM_COLS_AI + SITE_COLS)]:
    with mlflow.start_run(run_name=name) as run:
        pipe = make_pipe(cats, nums).fit(train[cats + nums], train.label_low_accrual, clf__sample_weight=train.w.values)
        m, p = evaluate(pipe, test[cats + nums], test.label_low_accrual, test.w)
        mlflow.log_params({"features": len(cats + nums), "split": "train<=2017,test>=2018", "train_rows": len(train), "test_rows": len(test)})
        mlflow.log_metrics(m)
        results[name] = dict(run_id=run.info.run_id, pipe=pipe, cols=cats + nums, proba=p, **m)
        print(name, {k: round(v, 4) for k, v in m.items()})

cmp = pd.DataFrame({k: {m: round(v[m], 4) for m in ["base_rate","roc_auc","pr_auc","top_decile_precision","top_decile_lift","top_decile_capture","brier"]}
                    for k, v in results.items()})
cmp["genai_lift"] = (cmp["design_plus_genai"] - cmp["design_only"]).round(4)
cmp["site_count_inflation"] = (cmp["leakage_check_with_site_counts"] - cmp["design_plus_genai"]).round(4)
display(cmp.reset_index().rename(columns={"index": "metric"}))

# COMMAND ----------

# MAGIC %md ## What drives low-accrual risk? (TreeSHAP contributions on the out-of-time test set)

# COMMAND ----------

best = results["design_plus_genai"]
pre, clf = best["pipe"].named_steps["pre"], best["pipe"].named_steps["clf"]
Xt = pre.transform(test[best["cols"]]); fn = pre.get_feature_names_out()
sv = clf.booster_.predict(Xt, pred_contrib=True)[:, :-1]   # LightGBM native TreeSHAP (last column = bias)
imp = pd.DataFrame({"feature": fn, "mean_abs_shap": np.abs(sv).mean(0)}).sort_values("mean_abs_shap", ascending=False).head(15)
display(imp)

# COMMAND ----------

# MAGIC %md ## Risk is actionable: observed low-accrual termination rate by predicted-risk decile (test set)

# COMMAND ----------

t = test[["label_low_accrual", "w"]].copy(); t["p"] = best["proba"]
t = t.sort_values("p"); t["cum_w"] = t.w.cumsum() / t.w.sum()
t["risk_decile"] = np.minimum(10, np.floor(t.cum_w * 10 - 1e-9).astype(int) + 1)   # population-weighted deciles (10 = riskiest)
t["pos_w"] = t.label_low_accrual * t.w
dec = t.groupby("risk_decile").agg(sample_rows=("p","size"), population_trials=("w","sum"), pos_w=("pos_w","sum")).reset_index()
dec["observed_low_accrual_rate"] = dec.pos_w / dec.population_trials
dec["lift_vs_avg"] = dec.observed_low_accrual_rate / (t.pos_w.sum() / t.w.sum())
dec = dec.drop(columns="pos_w")
display(dec.round(4))

# COMMAND ----------

# MAGIC %md ## Register the champion in Unity Catalog
# MAGIC The final model is refit on **all** labeled history (≤2022) with the validated hyper-parameters, then registered with alias `champion`.

# COMMAND ----------

from mlflow.models import infer_signature
cols = best["cols"]
final = make_pipe(CAT_COLS_DESIGN + CAT_COLS_AI, NUM_COLS_DESIGN + NUM_COLS_AI).fit(df[cols], df.label_low_accrual, clf__sample_weight=df.w.values)
with mlflow.start_run(run_name="champion_refit_all_history") as run:
    mlflow.log_metrics({f"oot_{k}": float(best[k]) for k in ["roc_auc","pr_auc","top_decile_lift","top_decile_capture"]})
    mlflow.log_metrics({f"oot_genai_lift_{k}": float(cmp.loc[k, "genai_lift"]) for k in ["roc_auc","pr_auc","top_decile_lift"]})
    mlflow.log_dict(imp.to_dict(orient="records"), "shap_top_features.json")
    info = mlflow.sklearn.log_model(final, name="model", input_example=df[cols].head(5),
                                    signature=infer_signature(df[cols].head(50), final.predict_proba(df[cols].head(50))[:, 1]),
                                    registered_model_name=MODEL_NAME)
from mlflow import MlflowClient
c = MlflowClient()
v = c.get_registered_model(MODEL_NAME).latest_versions if False else max(c.search_model_versions(f"name='{MODEL_NAME}'"), key=lambda x: int(x.version))
c.set_registered_model_alias(MODEL_NAME, "champion", v.version)
c.update_registered_model(MODEL_NAME, description="LightGBM: P(trial terminated for low accrual | design + GenAI eligibility features). Trained on ClinicalTrials.gov industry Phase 2/3 trials 2010-2022. Out-of-time validated (train<=2017, test>=2018).")
print(f"registered {MODEL_NAME} v{v.version} @champion; OOT ROC-AUC={best['roc_auc']:.3f}, top-decile lift={best['top_decile_lift']:.2f}x")
