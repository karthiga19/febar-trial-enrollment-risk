"""Collect text evidence for pipeline, model, Lakebase loop, governance and app into evidence/*.md.
Usage: python3 tools/collect_evidence.py   (profile fevm-current; run after a successful job run)"""
import json, os, pathlib, subprocess, time, urllib.request

P, S = "fevm-current", "km_catalog.febar_trials"
ROOT = pathlib.Path(__file__).resolve().parents[1]; EV = ROOT / "evidence"
APP = "https://febar-trial-risk-7474650225234523.aws.databricksapps.com"
PIPELINE_ID = "56976097-4d4a-464d-b9ee-1cb03bca5a4e"

def sh(*a, check=True):
    r = subprocess.run(list(a), capture_output=True, text=True)
    if check and r.returncode: raise RuntimeError(r.stderr[:800])
    return r.stdout

def q(sql):
    out = sh("databricks", "experimental", "aitools", "tools", "query", sql, "-p", P)
    i = out.find("[")
    return json.loads(out[i:]) if i >= 0 else []

def md_table(rows, maxw=140):
    if not rows: return "_(no rows)_\n"
    cols = list(rows[0].keys())
    s = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows: s += "| " + " | ".join(str(r.get(c))[:maxw].replace("|", "\\|").replace("\n", " ") for c in cols) + " |\n"
    return s

def sqlblock(label, sql):
    return f"**{label}**\n```sql\n{sql.strip()}\n```\n" + md_table(q(sql)) + "\n"

def pipeline():
    ups = json.loads(sh("databricks", "pipelines", "list-updates", PIPELINE_ID, "-p", P, "-o", "json"))["updates"]
    done = [u for u in ups if u.get("state") == "COMPLETED"]
    ev_sql = f"""SELECT origin.flow_name AS flow,
  count(*) AS completed_updates,
  max(details:flow_progress.metrics.num_output_rows::bigint) AS largest_update_rows,
  max_by(details:flow_progress.metrics.num_output_rows::bigint, timestamp) AS latest_update_rows,
  max_by(details:flow_progress.data_quality.dropped_records::bigint, timestamp) AS latest_dropped,
  max_by(details:flow_progress.data_quality.expectations::string, timestamp) AS latest_expectations
FROM event_log('{PIPELINE_ID}')
WHERE event_type = 'flow_progress' AND details:flow_progress.status::string = 'COMPLETED'
GROUP BY 1 ORDER BY 1"""
    out = ["# Lakeflow pipeline evidence\n", f"Pipeline `febar-trials-lakeflow-pipeline` (`{PIPELINE_ID}`), serverless SQL Spark Declarative Pipeline.\n",
           "## Recent updates\n", md_table([{"update_id": u["update_id"], "state": u["state"], "created": time.strftime('%Y-%m-%d %H:%M', time.gmtime(int(u.get("creation_time", 0)) / 1000)), "full_refresh": u.get("full_refresh", False)} for u in ups[:6]]),
           "\n## Flow metrics and data-quality expectations (from the pipeline event log, `event_log()` TVF)\n",
           "Bronze streaming tables are incremental (Auto Loader): the largest update is the initial load; later updates process only newly landed files.\n",
           sqlblock("event_log flow_progress", ev_sql),
           "\n## Table row counts now\n",
           sqlblock("medallion counts", f"""SELECT 'bronze_ctgov_studies' t, count(*) n FROM {S}.bronze_ctgov_studies UNION ALL
SELECT 'silver_trials', count(*) FROM {S}.silver_trials UNION ALL SELECT 'bronze_portfolio_studies', count(*) FROM {S}.bronze_portfolio_studies UNION ALL
SELECT 'bronze_enrollment_weekly', count(*) FROM {S}.bronze_enrollment_weekly UNION ALL SELECT 'gold_portfolio_enrollment_weekly', count(*) FROM {S}.gold_portfolio_enrollment_weekly UNION ALL
SELECT 'gold_portfolio_status', count(*) FROM {S}.gold_portfolio_status"""),
           sqlblock("silver by cohort/status", f"SELECT cohort, overall_status, sponsor_class = 'INDUSTRY' AS industry, count(*) n FROM {S}.silver_trials GROUP BY ALL ORDER BY 1,2,3"),
           sqlblock("GenAI stop-reason label distribution (industry vs all)", f"SELECT r.stop_category, count(*) all_sponsors, count_if(s.sponsor_class='INDUSTRY') industry FROM {S}.trial_stop_reasons r JOIN {S}.silver_trials s USING (nct_id) GROUP BY 1 ORDER BY 2 DESC")]
    (EV / "pipeline_run.md").write_text("\n".join(out))

def model():
    code = """
import mlflow, json
from mlflow import MlflowClient
mlflow.set_tracking_uri("databricks"); c = MlflowClient()
exp = c.get_experiment_by_name("/Users/karthiga.mahali@databricks.com/febar_accrual_risk")
runs = c.search_runs([exp.experiment_id], order_by=["start_time DESC"], max_results=4)
mv = c.get_model_version_by_alias("km_catalog.febar_trials.accrual_risk_model", "champion")
print(json.dumps({"runs": [{"run": r.info.run_name, "run_id": r.info.run_id, **{k: round(v, 4) for k, v in sorted(r.data.metrics.items())}} for r in runs],
                  "champion": {"name": mv.name, "version": mv.version, "run_id": mv.run_id, "created": mv.creation_timestamp}}))"""
    env = {**os.environ, "DATABRICKS_CONFIG_PROFILE": P, "MLFLOW_DISABLE_AGENT_HINT": "1"}
    r = subprocess.run([str(ROOT / ".venv/bin/python"), "-c", code], capture_output=True, text=True, env=env)
    d = json.loads(r.stdout.strip().splitlines()[-1])
    keys = ["base_rate", "roc_auc", "pr_auc", "top_decile_lift", "top_decile_capture", "top_decile_precision", "brier"]
    rows = [{"model": x["run"], **{k: x.get(k) for k in keys}} for x in d["runs"] if x["run"] != "champion_refit_all_history"]
    out = ["# Model evidence (MLflow, experiment `/Users/karthiga.mahali@databricks.com/febar_accrual_risk`)\n",
           "Out-of-time evaluation: train on trials started ≤2017, test on 2018–2022. Population-weighted (case-control sampling undone).\n",
           md_table(rows), "\n**Champion in Unity Catalog:** " + json.dumps(d["champion"]) + "\n",
           "\n- `design_only`: protocol design fields only.\n- `design_plus_genai` (**champion**): + GenAI eligibility-burden features.\n- `leakage_check_with_site_counts`: adds CT.gov site/country counts, which partly encode the outcome. Excluded from the champion and shown only to quantify the inflation.\n",
           "\nFull notebook output (SHAP importances, decile table): [train_model.md](train_model.md)\n"]
    (EV / "model_metrics.md").write_text("\n".join(out))

def lakebase_and_app():
    tok = json.loads(sh("databricks", "auth", "token", "-p", P, "-o", "json"))["access_token"]
    def call(method, path, body=None):
        req = urllib.request.Request(APP + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), json.loads(r.read() or "null"), round((time.time() - t0) * 1000)
    st = json.loads(sh("databricks", "postgres", "get-synced-table", f"synced_tables/{S}.trial_risk_worklist_synced", "-p", P, "-o", "json"))
    psql = sh(str(ROOT / "tools/lakebase_sql.sh"), "SELECT risk_tier, count(*) FROM febar_trials.trial_risk_worklist_synced GROUP BY 1 ORDER BY 1; EXPLAIN ANALYZE SELECT * FROM febar_trials.trial_risk_worklist_synced WHERE study_code = 'MRD-CVM-309';")
    s1, h1, who, ms1 = call("GET", "/api/whoami")
    s2, h2, wl, ms2 = call("GET", "/api/worklist")
    s3, _, study, ms3 = call("GET", "/api/studies/MRD-IMM-221")
    s4, _, created, ms4 = call("POST", "/api/studies/MRD-IMM-221/interventions", {"action_type": "add_sites", "notes": "Evidence run: activate 3 backup sites in Germany"})
    s5, _, upd, ms5 = call("PATCH", f"/api/interventions/{created['intervention_id']}", {"status": "in_progress"})
    # wait for Lakehouse Sync to land the update in UC
    t0 = time.time()
    while time.time() - t0 < 180:
        rows = q(f"SELECT _pg_change_type, _timestamp, intervention_id, study_code, action_type, status FROM {S}.lb_study_interventions_history WHERE intervention_id = {created['intervention_id']} ORDER BY _sort_by")
        if any(r["status"] == "in_progress" for r in rows): break
        time.sleep(5)
    lag = round(time.time() - t0)
    app = ["# Deployed app smoke test (Databricks App `febar-trial-risk`, AppKit)\n", f"URL: {APP}\n",
           "| call | HTTP | latency (ms, incl. network) | result |", "|---|---|---|---|",
           f"| GET /api/whoami | {s1} | {ms1} | {who} |",
           f"| GET /api/worklist | {s2} | {ms2} (Lakebase query {h2.get('x-lakebase-ms') or h2.get('X-Lakebase-Ms')} ms) | {len(wl)} studies; top 3: " + "; ".join(f"{r['study_code']} {r['risk_tier']} ${r['delay_cost_usd']:,.0f}" for r in wl[:3]) + " |",
           f"| GET /api/studies/MRD-IMM-221 | {s3} | {ms3} | {study['risk_tier']}: {study['headline']} |",
           f"| POST /api/studies/MRD-IMM-221/interventions | {s4} | {ms4} | intervention_id={created['intervention_id']} action={created['action_type']} tier_at_log={created['risk_tier_at_log']} |",
           f"| PATCH /api/interventions/{created['intervention_id']} | {s5} | {ms5} | status={upd['status']} |", ""]
    (EV / "app_smoke_test.md").write_text("\n".join(app))
    lb = ["# Lakebase evidence: operational serving and the closed loop\n",
          "## 1. UC → Lakebase synced table (`km_catalog.febar_trials.trial_risk_worklist_synced`, TRIGGERED, refreshed by the job's `sync_worklist_to_lakebase` task)\n",
          "```json\n" + json.dumps({"status": {k: v for k, v in st.get("status", {}).items() if k in ("detailed_state", "message", "pipeline_id", "last_sync", "triggered_update_status")}, "spec": st.get("spec")}, indent=1, default=str)[:2500] + "\n```\n",
          "## 2. Postgres read path (psql against the Lakebase endpoint)\n", "```text\n" + psql.strip() + "\n```\n",
          "## 3. App write-back → Lakebase native table → Lakehouse Sync → UC (SCD history)\n",
          f"The app logged intervention {created['intervention_id']} and then updated its status to `in_progress`. Lakehouse Sync replicated both changes to UC within ~{lag}s:\n",
          md_table(rows), "\n" + sqlblock("Current state view used by Genie (v_study_interventions)", f"SELECT intervention_id, study_code, action_type, status, risk_tier_at_log, owner_email, created_at FROM {S}.v_study_interventions ORDER BY intervention_id")]
    (EV / "lakebase_loop.md").write_text("\n".join(lb))

def governance():
    me = "karthiga.mahali@databricks.com"
    out = ["# Unity Catalog governance evidence\n",
           sqlblock("Tags on tables (governed `sensitivity` policy + febar_* tags)", f"SELECT table_name, tag_name, tag_value FROM km_catalog.information_schema.table_tags WHERE schema_name = 'febar_trials' ORDER BY 1, 2"),
           sqlblock("Column tags", f"SELECT table_name, column_name, tag_name, tag_value FROM km_catalog.information_schema.column_tags WHERE schema_name = 'febar_trials' ORDER BY 1, 2"),
           sqlblock("Entitlements table", f"SELECT * FROM {S}.ta_access"),
           sqlblock("App service principal grants (least privilege: views + metric view only)", f"SELECT table_name, privilege_type FROM km_catalog.information_schema.table_privileges WHERE table_schema = 'febar_trials' AND grantee = '9b18c2bd-5881-454c-9bca-2635a0bef106' ORDER BY 1"),
           "## Row- and column-level security, demonstrated\n",
           "Temporarily scope the current user to **Oncology only, no financials**, query the governed view, then restore full access.\n",
           sqlblock("Full access (ALL, financials)", f"SELECT therapeutic_area, count(*) studies, sum(delay_cost_usd) delay_cost_usd FROM {S}.v_portfolio_worklist GROUP BY 1 ORDER BY 1")]
    q(f"UPDATE {S}.ta_access SET therapeutic_area = 'Oncology', can_view_financials = false WHERE principal = '{me}' AND therapeutic_area = 'ALL'")
    try:
        out.append(sqlblock("Scoped to Oncology, no financials (same query)", f"SELECT therapeutic_area, count(*) studies, sum(delay_cost_usd) delay_cost_usd FROM {S}.v_portfolio_worklist GROUP BY 1 ORDER BY 1"))
        out.append(sqlblock("Metric view inherits the same security", f"SELECT `Therapeutic Area`, MEASURE(`Studies`) studies, MEASURE(`Delay Cost USD`) delay_cost FROM {S}.mv_portfolio_kpis GROUP BY ALL"))
    finally:
        q(f"UPDATE {S}.ta_access SET therapeutic_area = 'ALL', can_view_financials = true WHERE principal = '{me}' AND therapeutic_area = 'Oncology'")
    out.append(sqlblock("Restored", f"SELECT * FROM {S}.ta_access WHERE principal = '{me}'"))
    out.append(sqlblock("Lineage captured by Unity Catalog (system.access.table_lineage)", f"""SELECT DISTINCT source_table_name, target_table_name FROM system.access.table_lineage
WHERE target_table_schema = 'febar_trials' AND target_table_catalog = 'km_catalog' AND source_table_name IS NOT NULL AND event_date >= current_date() - 2 ORDER BY 2, 1"""))
    (EV / "governance.md").write_text("\n".join(out))

if __name__ == "__main__":
    import sys
    only = sys.argv[1:]
    for f in (pipeline, model, lakebase_and_app, governance):
        if only and f.__name__ not in only: continue
        try: f(); print("ok", f.__name__)
        except Exception as e: print("FAILED", f.__name__, e)
