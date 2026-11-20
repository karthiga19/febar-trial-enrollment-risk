# Trial Enrollment Risk Cockpit
### Find out which clinical trial will miss enrollment *before* it costs $18M, and know what to do about it

**Industry:** Life sciences, biopharma clinical operations · **Buyer:** VP Clinical Operations (exec sponsor) and clinical trial managers (domain owners)
**Customer (fictional):** *Meridian Therapeutics*, a mid-size sponsor with 24 active Phase 2/3 studies

---

## 1. The business problem

About **80% of clinical trials miss their enrollment timelines**, and *low accrual* is one of the most common reasons trials are terminated. Every day a Phase 3 trial runs late costs roughly **$40–55K in direct operating cost** (sites, CRO, monitoring). On top of that, each day of patent-protected sales lost at launch can cost **~$500K**.¹ Sponsors usually find out at the **quarterly portfolio review**, from a spreadsheet, months after the fix (more sites, a protocol amendment) would have been cheap.

## 2. The outcome this build delivers (numbers from the actual run)

| For | KPI | Result in this build |
|---|---|---|
| **VP Clinical Ops** | Studies at risk, found weeks earlier | **9 of 24** studies flagged (7 Critical, 2 High); **11** behind plan |
| | Projected direct cost of enrollment delay | **$87.5M** across the portfolio (3,118 study-days late) |
| | **Addressable by acting 12 weeks earlier** | **$24.3M** (direct cost only; lost-sales upside excluded) |
| **Trial managers** | Time to a defensible "what's wrong and what do I do" brief | AI brief per study, citing the numbers, in seconds instead of ~2 hours of status prep per study per month (~570 h/yr) |
| | The *right* fix, not just a red flag | A deterministic clinical-ops playbook picks the lever (amend protocol / add sites / recruitment / site remediation) from design risk and site activation, and GenAI explains it. MRD-IMM-224 (90th-percentile design risk) gets *amend*. MRD-CVM-309 (49th) gets *add sites*. |
| | Design risk known *before* first patient in | Model trained on **real ClinicalTrials.gov outcomes**. Trials in its top risk decile terminate for low accrual at **2.0× the base rate** (out-of-time, leakage-safe), and GenAI eligibility features lift ROC-AUC from 0.64 to 0.67 |

Assumptions (cost per day, detection advantage) live in a governed UC table, `value_assumptions`, owned by Clinical Finance, so the ROI can be challenged and changed without code.

## 3. What the user sees

**Trial Enrollment Risk Cockpit** (Databricks App, AppKit): https://febar-trial-risk-7474650225234523.aws.databricksapps.com

1. **KPI row:** studies at risk, studies behind plan, projected delay cost, addressable savings. Each tile reads the governed UC metric view.
2. **Ranked worklist** served from **Lakebase**. Click a study to see the GenAI brief, the model's top risk drivers (TreeSHAP), the most restrictive eligibility criteria, and actual-vs-plan enrollment.
3. **Log an intervention** ("Add sites", "Protocol amendment"…). It is written to Lakebase and **replicated back to Unity Catalog by Lakehouse Sync** within seconds.
4. **Ask Genie:** *"Which at-risk studies have no intervention logged yet?"* The answer includes the intervention you just logged, runs **on behalf of the user**, and shows the generated SQL.

## 4. The integrated data journey

```
 ClinicalTrials.gov API v2 (public, 49,677 trials)        Meridian CTMS + EDC weekly files (synthetic)
              │  tools/fetch_ctgov.py                                 │  tools/generate_portfolio.py
              ▼                                                       ▼
   UC Volume  /Volumes/km_catalog/febar_trials/raw/…   (landing zone; file-arrival trigger on EDC folder)
              │
 ① LAKEFLOW   Spark Declarative Pipeline (SQL, serverless): Auto Loader → bronze (VARIANT) → silver (expectations) → gold
              │      bronze_ctgov_studies · silver_trials · bronze_enrollment_weekly · gold_portfolio_enrollment_weekly · gold_portfolio_status
              ▼
 ③ GEN AI     ai_query + strict JSON schema (Claude Haiku 4.5)
              │      7,921 free-text "why stopped" → stop_category  ⇒ ML LABEL (2,790 low_accrual)
              │      4,800 eligibility texts → 14 protocol-burden features + top restrictive criteria
              ▼
 ③ ML         LightGBM, out-of-time validated, UC model accrual_risk_model@champion, TreeSHAP drivers
              │      scored portfolio + playbook action + Claude Sonnet 4.6 study brief → trial_risk_worklist (MERGE, CDF)
              ▼
 ② UNITY      tags (governed `sensitivity` policy) · row security by therapeutic area + $ column masking (ta_access + UDFs)
   CATALOG    governed views · metric view mv_portfolio_kpis · lineage · app SP least-privilege grants
              │
 ④ LAKEBASE   synced table (UC → Postgres, triggered)  ─────▶  App reads worklist (6 ms)
              │                                                App writes clinops.study_interventions
              │◀──────── Lakehouse Sync (Postgres → UC CDC) ── lb_study_interventions_history → v_study_interventions
              ▼
 ⑤ GENIE      "Meridian Trial Enrollment Risk Agent": metric view + 5 governed views, instructions, examples, benchmarks
              ▼
 ⑥ APP        AppKit (React + Node): analytics plugin (warehouse) · lakebase plugin · genie plugin (OBO)
```

One Lakeflow Job (`febar-trials-end-to-end`, DAB-managed) runs the whole chain: pipeline → GenAI → retrain gate → train → score → governance/semantic layer → Lakebase sync.

## 5. Evidence that it ran (all text, committed in [`evidence/`](evidence/))

| Evidence | File |
|---|---|
| End-to-end job run: every task with result and duration | [`evidence/JOB_RUN.md`](evidence/JOB_RUN.md) |
| Executed notebooks with real outputs (GenAI enrichment, training metrics, SHAP, scoring, briefs) | `evidence/genai_enrichment.md`, `evidence/train_model.md`, `evidence/score_portfolio.md` |
| Pipeline update: row counts and data-quality expectation results | [`evidence/pipeline_run.md`](evidence/pipeline_run.md) |
| Model metrics: design-only vs design + GenAI (MLflow) | [`evidence/model_metrics.md`](evidence/model_metrics.md) |
| Lakebase: synced table, latency, write-back, Lakehouse Sync CDC rows | [`evidence/lakebase_loop.md`](evidence/lakebase_loop.md) |
| Genie Agent: Conversation API transcripts with generated SQL and result rows | [`evidence/genie_conversations.md`](evidence/genie_conversations.md) |
| App API smoke test against the deployed app | [`evidence/app_smoke_test.md`](evidence/app_smoke_test.md) |
| Governance: tags, grants, row/column security demonstration | [`evidence/governance.md`](evidence/governance.md) |

## 6. Repo map

| Path | What |
|---|---|
| `databricks.yml`, `resources/` | DAB: pipeline + end-to-end job |
| `src/pipeline/*.sql` | Lakeflow Spark Declarative Pipeline (bronze/silver/gold) |
| `src/notebooks/02_genai_enrichment.py` | `ai_query` stop-reason label + eligibility feature extraction (incremental, batched) |
| `src/notebooks/03_train_accrual_risk_model.py` | LightGBM training, out-of-time eval, GenAI-lift comparison, UC registration |
| `src/notebooks/04_score_portfolio.py` | Scoring, TreeSHAP drivers, $ at risk, GenAI study briefs, MERGE to worklist |
| `src/sql/05_governance_semantic_layer.sql` | Tags, entitlements, row/column security, governed views, metric view |
| `app/` | AppKit app (own DAB): `server/routes/cockpit-routes.ts`, `client/src/components/*`, `config/queries/*.sql` |
| `tools/` | Data fetch/generation, Lakebase SQL, Genie Agent builder + eval, evidence exporter, SP grants |
| `docs/DECISIONS.md` | **Decisions and trade-offs** |
| `docs/AI_TEAMMATE.md` | How AI was used as a force multiplier (tools, prompts, failures fixed) |
| `docs/DEMO_SCRIPT.md` | Tell-show-tell demo and objection handling |
| `deck/` | Business presentation (Markdown + PDF) |

## 7. Reproduce

```bash
python3 tools/fetch_ctgov.py historical "COMPLETED|TERMINATED" 2010-01-01,2022-12-31   # ~48 pages
python3 tools/fetch_ctgov.py recruiting RECRUITING "" 2
python3 tools/generate_portfolio.py                                                    # synthetic sponsor feeds
databricks fs cp -r data/raw/historical dbfs:/Volumes/km_catalog/febar_trials/raw/ctgov/historical   # (+ recruiting, meridian)
databricks bundle deploy -p <profile> && databricks bundle run trials_e2e_job -p <profile>
# Lakebase: create project, synced table (tools/lakebase_setup.md), deploy app/ (cd app && databricks bundle deploy && databricks bundle run app)
python3 tools/build_genie_agent.py && python3 tools/genie_eval.py <space_id>
```

## Data and privacy

- **Public data:** ClinicalTrials.gov API v2 (U.S. National Library of Medicine), interventional Phase 2/3 trials started 2010–2022 plus a sample of currently recruiting trials.
- **Synthetic data:** sponsor name, study codes, study managers, sites and weekly enrollment are generated (`tools/generate_portfolio.py`, seeded). Study *designs* are templated from real recruiting trials (`source_nct_id` kept for lineage). **No customer data** is in this repo.

---
¹ Industry estimates (e.g. Tufts CSDD; widely cited ~80% enrollment-timeline miss rate). They are used as editable assumptions, not as findings of this build.
