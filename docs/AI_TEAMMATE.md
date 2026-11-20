# AI as a teammate: how this build was produced

**Tool:** Claude Code (CLI) on Claude Opus, driving the Databricks CLI against workspace `fevm-serverless-stable-35goml` (profile `fevm-current`).
**Elapsed:** about 1 working day, from a blank folder to a deployed app. The session ID is available on request.

## Working pattern

| Phase | What I (the SA) did | What the AI did |
|---|---|---|
| Problem framing | Chose life sciences. Pushed for a *specific* buyer problem and asked for a plain-language explanation of enrollment delay. | Proposed 4 life-sciences scenarios and recommended trial-enrollment risk, because ClinicalTrials.gov gives a **real label** (`why_stopped`) and **real unstructured text** (eligibility criteria). Explained the domain economics. |
| Design decisions | Approved: new Lakebase project, analytics + Lakebase app, Genie Agent design (approval gate). | Laid out trade-offs: warehouse vs Lakebase, synced table vs app-owned table, label definition, leakage guards. |
| Build | Reviewed outputs at each checkpoint. | Wrote every artifact (fetch script, SDP SQL, notebooks, DAB, governance SQL, AppKit app, docs) and ran them through the CLI. |
| Debugging | Watched. | Diagnosed and fixed real failures (below) from job error traces and system tables. |

## Databricks agent skills used

The Databricks Claude Code plugin's skills were loaded before each product area, so the AI followed current platform guidance instead of stale training data:
`databricks-core` · `databricks-pipelines` · `databricks-lakebase` · `databricks-apps` · `databricks-app-design` · `databricks-metric-views` · `databricks-genie-agents`.
These enforced a few things: confirm the profile before touching the workspace; present the Lakebase/analytics data-access decision; get approval before creating a live Genie Agent; ship all five AI-trust patterns on the Genie surface; never hardcode colors; always handle loading/empty/error states.

## Prompts and patterns that worked

1. **"Brainstorm first, don't build."** Separating the planning conversation from the build kept the scenario tied to a real buyer.
2. **"Explain it to me like I'm the customer."** Explaining enrollment delay in plain language produced the narrative the deck now opens with.
3. **Prove the prompt on 8 rows before running it on 8,000.** Each `ai_query` prompt was tested on a small sample on the SQL warehouse first (8/8 stop reasons correct, 2/2 eligibility extractions sensible) before the batch job ran.
4. **Measure, don't assume.** The model is trained twice (design-only vs design + GenAI features) so the value of the GenAI step is a measured number, not a claim.

## Real problems the AI caught and fixed during the build

| Symptom | Root cause | Fix |
|---|---|---|
| `bundle deploy` hung | DAB was syncing the 600 MB raw-data folder to the workspace | `sync.exclude` for `data/**` |
| Projected delay of 3,587 days | Near-zero run-rate makes the projection blow up | Cap at 730 days, flag stalled studies with "730+" |
| Test query took 5+ minutes | `ORDER BY … LIMIT` evaluated `ai_query` on every row before limiting | Limit in a subquery first |
| GenAI step on pace for 2+ hours | FM API batch throughput was about 3–5 rows/s across models (measured on Haiku, Gemini Flash, GPT-OSS and Sonnet) | **Case-control sampling** of controls with re-weighting in training; batched inserts that save progress |
| Serverless has no `.cache()` | Batch numbers would shift while inserting | Materialize the to-do list as a staging Delta table |
| `import shap` crashed | shap 0.46 is incompatible with numpy 2 on serverless | LightGBM native TreeSHAP (`pred_contrib=True`), one dependency fewer |
| MLflow `log_model` failed | SQL `DECIMAL` age columns are not JSON-serializable | Cast to `DOUBLE` in the feature SQL |
| No `CREATE CATALOG` on the metastore | Shared demo metastore | Synced table registered in the existing catalog |
| Workspace tag policies rejected tag values | Shared workspace enforces governed tags (`sensitivity` ∈ public/internal/pii; `source`, `domain` restricted) | Used the governed `sensitivity` values; prefixed custom tags `febar_*` |
| `n_sites` was the #1 model feature | Leakage: CT.gov drops never-activated sites from terminated trials | Removed from the champion; kept as a logged `leakage_check` run (AUC 0.709 vs 0.675) |
| LLM recommended "protocol amendment" for a low-design-risk study | LLMs don't reliably follow decision rules | Deterministic playbook in SQL decides; the LLM explains |
| Genie route returned `Invalid scope` | AppKit Genie plugin runs on-behalf-of the user | Added `user_api_scopes: [dashboards.genie]`, so user-level governance applies to Genie |
| Portfolio "enrollment vs plan" tile said 105% | Over-enrolling studies masked the laggards | Replaced with "studies behind plan" (honest-scale rule from the app-design skill) |

## Where human judgement mattered

- Picking the **label** ("terminated *for low accrual*") instead of "any termination". The stop-reason results confirm it: for industry sponsors, business decisions (1,486) outnumber low accrual (656).
- Keeping the **headline ROI on direct cost only**. The far larger lost-sales number is shown as upside, not as the claim.
- Using **fictional** sponsor data layered on real public trial designs, so no customer data is anywhere in the repo.
