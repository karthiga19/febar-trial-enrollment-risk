# 02_genai_enrichment (executed, with outputs)

Job run `1076184021196428` · task `genai_enrichment` · task run `291978907609572` · result **SUCCESS**

# 02 · GenAI enrichment — turn free text into a label and model features

ClinicalTrials.gov records two crucial things only as **free text**:

| Free text | What GenAI turns it into | Used for |
|---|---|---|
| `why_stopped` ("Slow accrual", "sponsor decision", "DSMB futility"…) | a **stop-reason category** | the ML **label** (terminated *because of low accrual*) |
| `eligibility_criteria` (median ~2,100 chars of inclusion/exclusion bullets) | **structured protocol-burden features** + therapeutic area + top restrictive criteria | ML **features** and the study-team **explanation** in the app |

Both passes use `ai_query` against a Databricks-hosted Claude model on the Foundation Model API, with a
**strict JSON schema** so every row comes back typed. Both are **incremental** (only trials not yet
enriched are sent to the model), so the scheduled job re-runs cheaply when Lakeflow lands new trials.

```python
dbutils.widgets.text("catalog", "km_catalog")
dbutils.widgets.text("schema", "febar_trials")
dbutils.widgets.text("model", "databricks-claude-haiku-4-5")
dbutils.widgets.text("negative_sample_pct", "20")   # case-control sampling of completed trials (see markdown below)
dbutils.widgets.text("batch_size", "500")
CAT, SCH, MODEL = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema"), dbutils.widgets.get("model")
NEG_PCT, BATCH = int(dbutils.widgets.get("negative_sample_pct")), int(dbutils.widgets.get("batch_size"))
spark.sql(f"USE {CAT}.{SCH}")
print(CAT, SCH, MODEL)
```
**Output:**

```text
km_catalog febar_trials databricks-claude-haiku-4-5
```

## A. Stop-reason classification → the ML label

```python
spark.sql("""
CREATE TABLE IF NOT EXISTS trial_stop_reasons (
  nct_id STRING, why_stopped STRING, stop_category STRING, stop_rationale STRING,
  ai_model STRING, enriched_at TIMESTAMP)
COMMENT 'GenAI (ai_query) classification of free-text ClinicalTrials.gov whyStopped into a stop-reason category. low_accrual = the ML label.'
""")

STOP_SCHEMA = """{"type":"json_schema","json_schema":{"name":"stop_reason","strict":true,"schema":{
 "type":"object","additionalProperties":false,"required":["category","rationale"],
 "properties":{
  "category":{"type":"string","enum":["low_accrual","safety","efficacy_futility","business_or_strategic","funding","covid_19","regulatory_or_site_operations","drug_supply","other","unclear"]},
  "rationale":{"type":"string"}}}}}"""

STOP_PROMPT = """You classify why a clinical trial was terminated, from the sponsor's free-text reason.
Categories:
- low_accrual: slow/insufficient/poor enrollment, recruitment or accrual; not enough eligible patients; competing trials took the patients.
- safety: adverse events, toxicity, safety signal, DSMB safety concern.
- efficacy_futility: lack of efficacy, futility at interim analysis, primary endpoint not met.
- business_or_strategic: sponsor/business/portfolio/strategic decision, company acquired, program discontinued (NOT due to enrollment).
- funding: loss of funding or budget.
- covid_19: stopped because of the COVID-19 pandemic.
- regulatory_or_site_operations: regulatory/IRB issues, PI left, site or operational problems unrelated to enrollment.
- drug_supply: study drug/device unavailable.
- other / unclear: anything else, or too vague to tell.
If several reasons are given, choose the primary one; if enrollment is mentioned as a reason at all, prefer low_accrual.
Give a <=15 word rationale.
Reason: """

STOP_PROMPT_SQL = STOP_PROMPT.replace("\\", "\\\\").replace("'", "\\'")
new = spark.sql("""SELECT count(*) n FROM silver_trials s
  WHERE overall_status='TERMINATED' AND why_stopped IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM trial_stop_reasons r WHERE r.nct_id = s.nct_id)""").first().n
print(f"terminated trials to classify this run: {new:,}")
```
**Output:**

```text
terminated trials to classify this run: 0
```

```python
spark.sql(f"""
INSERT INTO trial_stop_reasons
WITH todo AS (
  SELECT nct_id, why_stopped FROM silver_trials s
  WHERE overall_status='TERMINATED' AND why_stopped IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM trial_stop_reasons r WHERE r.nct_id = s.nct_id)
),
scored AS (
  SELECT nct_id, why_stopped,
    ai_query('{MODEL}', concat('{STOP_PROMPT_SQL}', why_stopped),
             responseFormat => '{STOP_SCHEMA}', failOnError => false) AS resp
  FROM todo
)
SELECT nct_id, why_stopped,
  from_json(resp.result, 'category STRING, rationale STRING').category,
  from_json(resp.result, 'category STRING, rationale STRING').rationale,
  '{MODEL}', current_timestamp()
FROM scored WHERE resp.errorMessage IS NULL
""")
display(spark.sql("""SELECT stop_category, count(*) AS trials, round(100*count(*)/sum(count(*)) OVER (),1) AS pct
                     FROM trial_stop_reasons GROUP BY 1 ORDER BY 2 DESC"""))
```
**Output:**

| stop_category | trials | pct |
|---|---|---|
| low_accrual | 2790 | 35.2 |
| business_or_strategic | 1780 | 22.5 |
| efficacy_futility | 1410 | 17.8 |
| regulatory_or_site_operations | 422 | 5.3 |
| safety | 408 | 5.2 |
| funding | 364 | 4.6 |
| covid_19 | 235 | 3.0 |
| drug_supply | 198 | 2.5 |
| unclear | 179 | 2.3 |
| other | 135 | 1.7 |


Spot-check: real free-text reasons and what the model decided.

```python
display(spark.sql("""SELECT stop_category, why_stopped, stop_rationale FROM trial_stop_reasons
                     WHERE length(why_stopped) BETWEEN 25 AND 160 ORDER BY hash(nct_id) LIMIT 15"""))
```
**Output:**

| stop_category | why_stopped | stop_rationale |
|---|---|---|
| efficacy_futility | The B5201003 OLE study was terminated based on the failure of the 'parent" B5201002 study to meet its efficacy endpoints. Termination was not due to safety. | Parent study B5201002 failed to meet efficacy endpoints; no safety concerns. |
| low_accrual | Difficulties in recruiting patients, compounded by problems extracting data from the device used in the study. | Difficulties recruiting patients; enrollment is primary reason mentioned. |
| business_or_strategic | Terminated early at the Sponsor's discretion, not due to safety concerns. | Sponsor discretion termination, explicitly not due to safety concerns. |
| business_or_strategic | Study TLK199.2107 was terminated for business reasons. | Sponsor terminated study for business reasons. |
| regulatory_or_site_operations | study closed prematurely because investigator left National Institutes of Health | Principal investigator left the National Institutes of Health site. |
| efficacy_futility | Lack of efficacy - Inability to meet the primary response endpoint | Failed to meet primary response endpoint; lack of efficacy demonstrated. |
| low_accrual | Slow recruitment, lack of continued funding | Slow recruitment mentioned; enrollment issues take priority over funding. |
| low_accrual | The study enrollment is not enough | Insufficient enrollment; not enough patients enrolled in the study. |
| business_or_strategic | Sponsor business decision, not safety related | Sponsor made business decision to terminate trial; not safety-related. |
| safety | The benefit-risk profile no longer supports continuing the studies | Benefit-risk profile no longer favorable; safety concerns outweigh potential benefits. |
| low_accrual | PI opted to close study due to poor accrual. | Principal investigator closed study due to poor accrual and insufficient enrollment. |
| low_accrual | The study was terminated early due to difficulty in enrollment and lack of clinical study drug access. | Difficulty in enrollment is primary reason; drug supply also mentioned. |
| business_or_strategic | Due to Interim Analysis and business concerns | Interim analysis showed concerns; business decision to discontinue trial. |
| regulatory_or_site_operations | The study was terminated because the Study Chair/IDE Sponsor and Novocure determined that conducting this trial was not feasible without CMS approval. | Study not feasible without CMS approval; regulatory requirement prevented continuation. |
| business_or_strategic | Bayer terminated the program and sold the IP to Medronic | Sponsor terminated program and sold IP; strategic business decision. |


## B. Eligibility-criteria extraction → protocol-burden features
**Scope (case-control design):** low-accrual terminations are rare (~4% of industry trials), and FM API batch throughput
is a few rows/second, so we extract eligibility features for
* **every** industry trial terminated for low accrual (the positives),
* a deterministic **`negative_sample_pct`% sample** of industry trials that completed (the controls). Notebook 03 re-weights them,
* the recruiting landscape (50% sample) and **all** Meridian portfolio design templates.

Rows are processed in batches of `batch_size`, so a long run saves progress as it goes and re-runs only pick up what is missing.

```python
spark.sql("""
CREATE TABLE IF NOT EXISTS trial_eligibility_ai (
  nct_id STRING, therapeutic_area STRING, n_inclusion INT, n_exclusion INT,
  requires_biomarker BOOLEAN, requires_prior_therapy_failure BOOLEAN, excludes_prior_therapy BOOLEAN,
  requires_lab_thresholds BOOLEAN, requires_performance_status BOOLEAN, excludes_common_comorbidities BOOLEAN,
  requires_invasive_procedure BOOLEAN, requires_washout BOOLEAN, narrow_population BOOLEAN,
  complexity_score INT, top_restrictive_criteria ARRAY<STRING>, ai_model STRING, enriched_at TIMESTAMP)
COMMENT 'GenAI (ai_query) structured extraction of protocol eligibility burden from free-text inclusion/exclusion criteria'
""")

ELIG_FIELDS = {
 "therapeutic_area": {"type":"string","enum":["oncology","cardiometabolic","neuroscience","immunology","infectious_disease","respiratory","rare_disease","psychiatry","other"]},
 "n_inclusion": {"type":"integer"}, "n_exclusion": {"type":"integer"},
 "requires_biomarker": {"type":"boolean"}, "requires_prior_therapy_failure": {"type":"boolean"},
 "excludes_prior_therapy": {"type":"boolean"}, "requires_lab_thresholds": {"type":"boolean"},
 "requires_performance_status": {"type":"boolean"}, "excludes_common_comorbidities": {"type":"boolean"},
 "requires_invasive_procedure": {"type":"boolean"}, "requires_washout": {"type":"boolean"},
 "narrow_population": {"type":"boolean"},
 "complexity_score": {"type":"integer"},
 "top_restrictive_criteria": {"type":"array","items":{"type":"string"}},
}
import json
ELIG_SCHEMA = json.dumps({"type":"json_schema","json_schema":{"name":"eligibility","strict":True,"schema":{
  "type":"object","additionalProperties":False,"required":list(ELIG_FIELDS),"properties":ELIG_FIELDS}}})
ELIG_DDL = ("therapeutic_area STRING, n_inclusion INT, n_exclusion INT, requires_biomarker BOOLEAN, "
  "requires_prior_therapy_failure BOOLEAN, excludes_prior_therapy BOOLEAN, requires_lab_thresholds BOOLEAN, "
  "requires_performance_status BOOLEAN, excludes_common_comorbidities BOOLEAN, requires_invasive_procedure BOOLEAN, "
  "requires_washout BOOLEAN, narrow_population BOOLEAN, complexity_score INT, top_restrictive_criteria ARRAY<STRING>")

ELIG_PROMPT = """You are a clinical operations feasibility expert. Read the trial's eligibility criteria and extract how
burdensome they are for patient recruitment.
- n_inclusion / n_exclusion: number of distinct inclusion / exclusion criteria (count bullets or numbered items; sub-bullets belong to their parent).
- requires_biomarker: a genetic, molecular, receptor or lab biomarker status is required (e.g. HER2+, EGFR mutation, PD-L1, HLA type).
- requires_prior_therapy_failure: patients must have failed/progressed on or be refractory/intolerant to prior therapy.
- excludes_prior_therapy: patients must be treatment-naive or are excluded for specific prior treatments.
- requires_lab_thresholds: specific lab value cut-offs (e.g. ANC, eGFR, HbA1c, LVEF ranges).
- requires_performance_status: ECOG/Karnofsky/functional status requirement.
- excludes_common_comorbidities: excludes common conditions (e.g. diabetes, hypertension, prior cancer, cardiovascular disease, hepatic/renal impairment).
- requires_invasive_procedure: biopsy, endoscopy, lumbar puncture, catheterization etc. required for eligibility or study.
- requires_washout: a washout period from current/prior medications is required.
- narrow_population: the population is rare or tightly defined (rare disease, narrow subtype/stage, narrow age band).
- complexity_score: 1 (very easy to recruit) to 10 (extremely restrictive), relative to typical Phase 2/3 trials.
- top_restrictive_criteria: up to 3 short phrases (<=12 words each) naming the criteria most likely to shrink the eligible pool.
Conditions: {cond}
Eligibility criteria:
{text}"""

todo_sql = f"""
WITH scope AS (
  SELECT s.nct_id, s.conditions, s.cohort, substring(s.eligibility_criteria, 1, 9000) AS elig,
         CASE WHEN s.overall_status='TERMINATED' AND r.stop_category='low_accrual' THEN 1
              WHEN s.overall_status='COMPLETED' THEN 0 END AS y
  FROM silver_trials s LEFT JOIN trial_stop_reasons r USING (nct_id)
  WHERE s.sponsor_class = 'INDUSTRY' AND s.eligibility_criteria IS NOT NULL
)
SELECT nct_id, conditions, elig FROM scope s
WHERE ( (cohort = 'historical' AND (y = 1 OR (y = 0 AND pmod(hash(nct_id), 100) < {NEG_PCT})))
     OR (cohort = 'recruiting' AND (pmod(hash(nct_id), 100) < 50
                                    OR nct_id IN (SELECT source_nct_id FROM silver_portfolio_studies))) )
  AND NOT EXISTS (SELECT 1 FROM trial_eligibility_ai e WHERE e.nct_id = s.nct_id)"""
# materialize the to-do list (stable batch numbers while we insert)
spark.sql(f"""CREATE OR REPLACE TABLE _elig_todo AS
  SELECT *, floor((row_number() OVER (ORDER BY nct_id) - 1) / {BATCH}) AS batch FROM ({todo_sql})""")
n_todo = spark.table("_elig_todo").count()
n_batches = spark.sql("SELECT coalesce(max(batch) + 1, 0) FROM _elig_todo").first()[0]
print(f"trials to extract this run: {n_todo:,} in {n_batches} batches of {BATCH}")
```
**Output:**

```text
trials to extract this run: 0 in 0 batches of 500
```

```python
import time
prompt_sql = ELIG_PROMPT.replace("'", "\\'").replace("{cond}", "', coalesce(conditions,''), '").replace("{text}", "', elig, '")
for b in range(n_batches):
    t0 = time.time()
    spark.sql(f"""
    INSERT INTO trial_eligibility_ai
    WITH scored AS (
      SELECT nct_id, ai_query('{MODEL}', concat('{prompt_sql}'),
                              responseFormat => '{ELIG_SCHEMA}', failOnError => false) AS resp
      FROM _elig_todo WHERE batch = {b}
    ),
    parsed AS (SELECT nct_id, from_json(resp.result, '{ELIG_DDL}') AS j FROM scored WHERE resp.errorMessage IS NULL)
    SELECT nct_id, j.therapeutic_area, j.n_inclusion, j.n_exclusion, j.requires_biomarker, j.requires_prior_therapy_failure,
      j.excludes_prior_therapy, j.requires_lab_thresholds, j.requires_performance_status, j.excludes_common_comorbidities,
      j.requires_invasive_procedure, j.requires_washout, j.narrow_population,
      greatest(1, least(10, j.complexity_score)), slice(j.top_restrictive_criteria, 1, 3), '{MODEL}', current_timestamp()
    FROM parsed
    """)
    print(f"batch {b + 1}/{n_batches} done in {time.time() - t0:.0f}s")
```
```python
display(spark.sql("""SELECT therapeutic_area, count(*) trials, round(avg(n_exclusion),1) avg_exclusions,
  round(avg(complexity_score),1) avg_complexity, round(100*avg(cast(requires_biomarker AS INT)),1) pct_biomarker
  FROM trial_eligibility_ai GROUP BY 1 ORDER BY 2 DESC"""))
```
**Output:**

| therapeutic_area | trials | avg_exclusions | avg_complexity | pct_biomarker |
|---|---|---|---|---|
| oncology | 1097 | 11.6 | 7.4 | 50.8 |
| other | 1033 | 11.9 | 5.8 | 10.5 |
| rare_disease | 637 | 10.4 | 7.4 | 52.3 |
| infectious_disease | 582 | 11.8 | 6.5 | 55.7 |
| cardiometabolic | 426 | 10.8 | 6.2 | 29.3 |
| respiratory | 278 | 12.9 | 6.6 | 20.1 |
| immunology | 261 | 10.2 | 6.6 | 36.8 |
| neuroscience | 244 | 10.4 | 6.9 | 27.0 |
| psychiatry | 205 | 9.5 | 6.6 | 7.3 |
| ophthalmology | 28 | 7.2 | 5.8 | 3.6 |
| dermatology | 3 | 9.3 | 5.0 | 0.0 |
| gastroenterology | 3 | 7.0 | 5.3 | 0.0 |
| endocrinology | 2 | 17.5 | 7.0 | 50.0 |
| cardiology | 1 | 28.0 | 8.0 | 0.0 |


Spot-check a few extractions next to the real criteria text.

```python
display(spark.sql("""SELECT e.nct_id, e.therapeutic_area, e.n_inclusion, e.n_exclusion, e.complexity_score,
  e.top_restrictive_criteria, substring(s.eligibility_criteria, 1, 400) AS criteria_excerpt
  FROM trial_eligibility_ai e JOIN silver_trials s USING (nct_id) ORDER BY hash(e.nct_id) LIMIT 8"""))
```
**Output:**

| nct_id | therapeutic_area | n_inclusion | n_exclusion | complexity_score | top_restrictive_criteria | criteria_excerpt |
|---|---|---|---|---|---|---|
| NCT01521533 | oncology | 11 | 15 | 7 | ['Bortezomib-naive or bortezomib-sensitive with 6-month sustained PR', 'Prior allogeneic stem cell transplant exclusion', 'Significant neuropathy (grade 2+) exc | Inclusion Criteria:  1. Male or female, aged ≥ 18 years. 2. Diagnosis of relapsed multiple myeloma for which bortezomib/dexamethasone would be given as standard |
| NCT06439277 | other | 3 | 6 | 7 | ['BMI ≥95th percentile plus 2 comorbidities', 'HbA1c >6.4% or type 2 diabetes exclusion', 'Recent weight loss >5kg or bariatric surgery exclusion'] | Inclusion Criteria:  * Have body mass index (BMI) equal to or above the 95th percentile for age and sex (on age and gender-specific growth chart for diagnosis o |
| NCT01142778 | oncology | 3 | 4 | 7 | ['HER2-positive biomarker requirement', 'Treatment-naive (no prior chemotherapy/radiation/hormonal therapy)', 'Early stage disease with neoadjuvant therapy cand | Inclusion Criteria:  * Participants with early stage HER2-positive breast cancer * Scheduled to receive neoadjuvant therapy with the objective of conservative s |
| NCT02207634 | cardiometabolic | 1 | 1 | 3 | ['Prior randomization into FOURIER study', 'Dementia or mild cognitive impairment exclusion'] | Inclusion Criteria:  * Randomized into Study 20110118 (FOURIER; NCT01764633)  Exclusion Criteria:  * Current or known past diagnosis of dementia or mild cogniti |
| NCT03922542 | rare_disease | 1 | 6 | 6 | ['Documented keratoconus or ectasia diagnosis required', 'Insufficient corneal thickness exclusion', 'Conditions interfering with epithelial healing'] | Inclusion Criteria:  * Documented keratoconus or ectasia after refractive surgery  Exclusion Criteria:  * Insufficient corneal thickness * Ocular condition that |
| NCT01054092 | cardiometabolic | 3 | 7 | 4 | ['HbA1c 6.5-9.5% range requirement', 'Exclusion of significant renal/hepatic/cardiovascular disease', 'Proteinuria and elevated creatinine exclusions'] | Inclusion Criteria:  * Type 2 diabetic patients for at least 12 weeks * HbA1c value between 6.5 and 9.5% * Body Mass Index ( BMI )20.0 - 45.0kg/m2  Exclusion Cr |
| NCT01478997 | other | 4 | 15 | 6 | ['Strict pain VAS range (40-80)', 'Multiple medication washout periods', 'Exclusion of common comorbidities (diabetes, hypertension, cardiovascular disease)'] | Inclusion Criteria:  * Ambulatory male or female patients aged 30-65 years, and diagnosed of OA of the knee according to the ACR clinical and radiographic crite |
| NCT02499783 | immunology | 5 | 7 | 7 | ['Chinese descent with full Chinese parentage', 'CDAI 220-450 despite corticosteroids/immunosuppressants', 'Elevated hs-CRP biomarker requirement'] | Inclusion Criteria:  * Subjects of Chinese descent with full Chinese parentage. * Diagnosis of Crohn's disease (CD) for at least 3 months prior to Week 0. * Cro |


## Coverage / quality gate

```python
cov = spark.sql("""
SELECT
  (SELECT count(*) FROM silver_trials WHERE overall_status='TERMINATED' AND why_stopped IS NOT NULL) AS terminated_with_reason,
  (SELECT count(*) FROM trial_stop_reasons) AS stop_reasons_classified,
  (SELECT count(*) FROM _elig_todo) AS eligibility_attempted_this_run,
  (SELECT count(*) FROM trial_eligibility_ai) AS eligibility_extracted
""").first().asDict()
print(cov)
assert cov["stop_reasons_classified"] >= 0.97 * cov["terminated_with_reason"], "stop-reason coverage < 97%"
assert spark.sql(todo_sql).count() <= 0.03 * cov["eligibility_extracted"], "eligibility extraction: >3% of in-scope trials failed"
spark.sql("DROP TABLE IF EXISTS _elig_todo")
print("coverage gate passed")
```
**Output:**

```text
{'terminated_with_reason': 7921, 'stop_reasons_classified': 7921, 'eligibility_attempted_this_run': 0, 'eligibility_extracted': 4800}
coverage gate passed
```
