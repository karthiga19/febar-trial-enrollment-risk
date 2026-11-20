# Decisions and trade-offs

Each decision lists what was chosen, the alternative that was rejected, and why.

## Problem framing

| Decision | Alternative | Why |
|---|---|---|
| **Two signals: design risk (ML) and operational risk (actual vs plan)** | Operational tracking only (the usual CTMS dashboard) | Actual-vs-plan only flags a study after it is already behind. The design-risk score is available on day 1, before first patient in, and also explains *why* a study is likely to struggle (restrictive criteria). Together they answer "which study needs action this week, and what action". |
| **Label = terminated for *low accrual*, classified by GenAI from free text** | Label = any termination | Most terminations are not enrollment failures (business decisions, futility, safety). Mixing them would teach the model the wrong thing. CT.gov has no coded reason, only free text, so an LLM classifier is the only scalable way to build the label. 8/8 spot-checked labels were correct (see `evidence/`). |
| **Industry-sponsored trials only for training** | All sponsors (academic, NIH) | The buyer is a pharma sponsor. Academic trials have different recruitment dynamics and termination drivers. It also keeps GenAI cost bounded (~25K extractions instead of ~50K). |
| **Out-of-time split (train ≤2017, test 2018-2022)** | Random split | A random split leaks era effects (COVID, regulatory changes) and overstates accuracy. The out-of-time split matches how the model is actually used: trained on the past, applied to future protocols. |
| **Never use actual enrollment, completion date or status as features** | Use every column | These are outcomes, not design inputs, so using them would leak the answer. Only protocol-design fields known before FPI are used. |
| **Exclude CT.gov site/country counts from the champion** | Keep the top-ranked feature | `n_sites` was the #1 SHAP feature, but terminated trials often list fewer sites because sites that never activated get dropped from the record. Site counts therefore partly encode the outcome. A separate `leakage_check_with_site_counts` run shows they would inflate ROC-AUC from 0.675 to 0.709. The more honest model was kept. |

## Platform choices

| Decision | Alternative | Why |
|---|---|---|
| **Lakeflow Spark Declarative Pipelines (SQL) with Auto Loader on a UC Volume** | Ad-hoc notebooks with `spark.read` | Incremental exactly-once ingestion, declarative expectations (data quality is visible in the event log), and automatic lineage. The landing zone stands in for an S3 drop from the CTMS/EDC vendor, and a **file-arrival trigger** on the enrollment folder runs the whole job when a new weekly EDC file lands. |
| **Bronze stores the full CT.gov record as `VARIANT`** | Inferred nested struct schema | CT.gov adds and renames fields regularly. VARIANT keeps ingestion stable under schema drift, and silver chooses the fields it needs. |
| **GenAI enrichment as a separate incremental notebook task, not inside the pipeline** | `ai_query` inside a materialized view | `ai_query` is non-deterministic, so an MV would recompute (and re-bill) every row on each full refresh. The notebook only sends *new* trials to the model (anti-join on the enrichment table), so weekly re-runs cost cents. |
| **`ai_query` + strict JSON schema on Claude Haiku 4.5** for bulk extraction; **Claude Sonnet 4.6** for the 24 study briefs | `ai_extract`, or one large model everywhere | Strict `json_schema` guarantees typed output (enums, booleans, ints) for the ~30K bulk calls. Haiku keeps those calls cheap. Sonnet is used only where wording quality matters (24 briefs per run). Note: Sonnet 5.x is not batch-enabled in `ai_query`, which ruled it out for the bulk calls. |
| **LightGBM + one-hot in an sklearn Pipeline, registered in UC with alias `@champion`** | AutoML, deep learning, or an LLM judging risk directly | Tabular data with about 25K rows, and SHAP explanations are needed per study. An LLM gives no calibrated probability and no out-of-time validation. AutoML would work, but this is simpler to explain and reproduce. |
| **Risk shown as a percentile vs ~25K historical trials** | Raw probability | `scale_pos_weight` makes raw probabilities uncalibrated. "Riskier than 91% of comparable trials" is what a study manager can act on. |
| **A deterministic playbook picks the action and the LLM explains it** | Let the LLM choose the action | In testing the LLM chose "protocol amendment" for a study in the 10th percentile of design risk, even with the playbook in the prompt. Decisions must be auditable and consistent: SQL `CASE` rules (no delay → monitor; <80% sites active → remediation; design risk ≥70th percentile → amendment; ≥90% sites active → add sites; else recruitment). The LLM writes the brief and the rationale *for* that action. |
| **$ assumptions in a governed UC table (`value_assumptions`)** | Constants in code | Finance owns the numbers and can change them without a deploy. The headline ROI uses **direct cost only**. Lost-sales upside is stored but deliberately excluded from the headline. |

## Serving and the closed loop

| Decision | Alternative | Why |
|---|---|---|
| **Lakebase (Postgres) for the operational worklist plus native write-back table** | App queries the SQL warehouse for everything | The cockpit is an operational tool, used many times a day for row lookups and writes. A warehouse is the wrong engine for transactional writes. Lakebase gives fast reads on the synced worklist and ACID writes for interventions. |
| **Synced table (UC → Lakebase) for the worklist** | App writes the worklist itself | UC stays the single source of truth for model output. The sync is managed, with no custom ETL. |
| **Lakehouse Sync (Lakebase → UC, CDC history) for interventions** | Nightly export job | Interventions logged in the app land back in UC as an SCD-2 history table automatically. That closes the loop: Genie can answer "which at-risk studies have no intervention logged?", and the history becomes training data for intervention effectiveness. |
| **SQL warehouse (AppKit analytics plugin) for KPI tiles and trend charts** | Lakebase for everything | Aggregations and time series over the gold tables and metric view belong on the warehouse. Each engine does what it is good at. |

## Governance

| Decision | Alternative | Why |
|---|---|---|
| **Consumers read governed views (`v_portfolio_worklist`, `mv_portfolio_kpis`), never raw tables** | Grant SELECT on tables | Row-level security by therapeutic area and column-level masking of $ live in one place (an entitlement table plus two SQL UDFs). Genie, the app and BI inherit them without separate configuration. |
| **Entitlement mapping table** | `is_account_group_member()` with account groups | Works without account-admin rights in a shared demo workspace. In production you would switch to groups. |
| **Metric view for portfolio KPIs** | KPI SQL repeated in the app, Genie and dashboards | One definition of "At-Risk Studies" and "Delay Cost USD". Genie and the app return the same number. |
| **Tags: `data_classification` = public / confidential / internal** | Naming conventions | Makes it visible that public CT.gov data and confidential sponsor data sit side by side, and is searchable in Catalog Explorer. |

## What I would do next (out of scope for a 1-day build)

- Calibrate probabilities (isotonic) and add an MLflow evaluation of the GenAI extraction against a hand-labeled set of 100 protocols.
- Site-level model (which *sites* will under-enroll) using the EDC site history.
- Use the intervention history (Lakehouse Sync) to measure which lever (add sites vs amendment) actually recovers enrollment.
- Replace the entitlement table with account groups. Serve the model on Model Serving for what-if protocol scoring inside the app.
