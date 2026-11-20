"""Create/update the 'Meridian Trial Enrollment Risk Agent' Genie Agent from code (reproducible).
Usage: python3 tools/build_genie_agent.py [--space-id ID]   (uses databricks CLI profile fevm-current)
"""
import json, subprocess, sys, hashlib

PROFILE, WH, S = "fevm-current", "734ae882913255c9", "km_catalog.febar_trials"
hid = lambda s: hashlib.md5(s.encode()).hexdigest()   # deterministic 32-hex ids

TABLES = [
    (f"{S}.v_enrollment_weekly", [("week_ending", "Friday week-ending date of the EDC enrollment extract")]),
    (f"{S}.v_portfolio_worklist", [
        ("risk_tier", "Critical | High | Watch | On track (see instructions)"),
        ("pct_of_plan", "randomized_to_date / planned_to_date; < 1 means behind plan"),
        ("design_risk_percentile", "model risk of low-accrual termination vs historical industry trials (0-100, higher = riskier)"),
        ("projected_delay_days", "projected last-patient-in delay vs plan in days, capped at 730"),
        ("delay_cost_usd", "projected direct cost of the delay in USD (NULL if the user lacks financial entitlement)"),
        ("recommended_action", "GenAI recommended lever: add_sites, protocol_amendment, recruitment_campaign, site_remediation, monitor")]),
    (f"{S}.v_study_interventions", [("action_type", "intervention logged by the study team in the cockpit app")]),
    (f"{S}.v_trial_landscape", [
        ("cohort", "historical = completed/terminated 2010-2022 (sampled), recruiting = currently recruiting"),
        ("terminated_for_low_accrual", "TRUE if terminated and the GenAI stop-reason classifier labeled it low_accrual"),
        ("requires_biomarker", "GenAI-extracted: eligibility requires a biomarker/genetic status")]),
    (f"{S}.value_assumptions", []),
]
METRIC_VIEWS = [f"{S}.mv_portfolio_kpis"]

INSTRUCTIONS = """You support Meridian Therapeutics clinical operations (fictional sponsor). Portfolio = 24 active studies.
- Portfolio questions: use v_portfolio_worklist (one row per study) or the metric view mv_portfolio_kpis (use MEASURE() for KPIs like `At Risk Studies`, `Delay Cost USD`, `Enrollment Vs Plan`).
- Risk tiers: Critical = projected delay > 120 days or < 60% of plan; High = > 45 days, or design_risk_percentile >= 80 and < 90% of plan; Watch = design_risk_percentile >= 70 or < 95% of plan; otherwise On track. "At risk" means Critical or High.
- "Behind plan" means pct_of_plan < 1. Show pct_of_plan as a percentage.
- Always include study_code (e.g. MRD-CVM-309) and therapeutic_area when listing studies; order by risk tier (Critical, High, Watch, On track), then delay_cost_usd desc.
- Enrollment trends over time: v_enrollment_weekly (randomized_cum = actual cumulative, planned_cum = plan).
- Interventions: v_study_interventions holds the current state of actions logged by study managers in the app (status open/in_progress/done/cancelled). "No intervention logged" = no row in v_study_interventions for that study_code.
- v_trial_landscape is PUBLIC ClinicalTrials.gov data for benchmarking. Never mix it into Meridian portfolio KPIs. Historical cohort is case-control sampled (all low-accrual terminations, 20% of completed trials), so report rates as "in this sample" or compare groups relative to each other.
- Dollar figures come from value_assumptions (direct cost per day by phase). Lost sales are upside only, never part of delay cost.
- Dates: as_of_week is the latest data week."""

EXAMPLES = [
    ("Which studies are Critical or High risk and why?",
     f"SELECT study_code, therapeutic_area, phase, risk_tier, round(pct_of_plan*100,0) AS pct_of_plan, projected_delay_days, delay_cost_usd, design_risk_percentile, recommended_action, headline FROM {S}.v_portfolio_worklist WHERE risk_tier IN ('Critical','High') ORDER BY CASE risk_tier WHEN 'Critical' THEN 1 ELSE 2 END, delay_cost_usd DESC"),
    ("What is the total projected delay cost by therapeutic area?",
     f"SELECT `Therapeutic Area`, MEASURE(`Delay Cost USD`) AS delay_cost_usd, MEASURE(`At Risk Studies`) AS at_risk_studies, MEASURE(`Studies`) AS studies FROM {S}.mv_portfolio_kpis GROUP BY ALL ORDER BY delay_cost_usd DESC"),
    ("Which at-risk studies have no intervention logged yet?",
     f"SELECT w.study_code, w.therapeutic_area, w.risk_tier, w.delay_cost_usd, w.recommended_action FROM {S}.v_portfolio_worklist w WHERE w.risk_tier IN ('Critical','High') AND NOT EXISTS (SELECT 1 FROM {S}.v_study_interventions i WHERE i.study_code = w.study_code) ORDER BY w.delay_cost_usd DESC"),
    ("Show actual vs planned enrollment for MRD-CVM-309",
     f"SELECT week_ending, randomized_cum AS actual, planned_cum AS plan FROM {S}.v_enrollment_weekly WHERE study_code = 'MRD-CVM-309' ORDER BY week_ending"),
    ("Among public oncology Phase 3 trials, how often do biomarker-selected trials terminate for low accrual vs non-biomarker?",
     f"SELECT requires_biomarker, count(*) AS trials, round(100*avg(cast(terminated_for_low_accrual AS INT)),1) AS pct_low_accrual_in_sample FROM {S}.v_trial_landscape WHERE cohort='historical' AND therapeutic_area='oncology' AND phase IN ('PHASE3','PHASE2/3') GROUP BY requires_biomarker"),
]
BENCH = EXAMPLES + [
    ("How many studies are behind plan?", f"SELECT count(*) AS studies_behind_plan FROM {S}.v_portfolio_worklist WHERE pct_of_plan < 1"),
]

def build():
    tables = []
    for ident, cols in sorted(TABLES):
        t = {"identifier": ident}
        if cols:
            t["column_configs"] = sorted([{"column_name": c, "description": [d]} for c, d in cols], key=lambda x: x["column_name"])
        tables.append(t)
    payload = {
        "version": 2,
        "config": {"sample_questions": sorted([{"id": hid("sq" + q), "question": [q]} for q, _ in EXAMPLES], key=lambda x: x["id"])},
        "data_sources": {"tables": tables, "metric_views": [{"identifier": m} for m in sorted(METRIC_VIEWS)]},
        "instructions": {
            "text_instructions": [{"id": hid("ti"), "content": [INSTRUCTIONS]}],
            "example_question_sqls": sorted([{"id": hid("ex" + q), "question": [q], "sql": [s]} for q, s in EXAMPLES], key=lambda x: x["id"]),
        },
        "benchmarks": {"questions": sorted([{"id": hid("bm" + q), "question": [q], "answer": [{"format": "SQL", "content": [s]}]} for q, s in BENCH], key=lambda x: x["id"])},
    }
    return json.dumps(payload)

if __name__ == "__main__":
    space = sys.argv[sys.argv.index("--space-id") + 1] if "--space-id" in sys.argv else None
    body = {"warehouse_id": WH, "serialized_space": build(), "title": "Meridian Trial Enrollment Risk Agent",
            "description": "Ask about Meridian Therapeutics' clinical-trial enrollment risk: at-risk studies, delay cost, interventions, enrollment vs plan, and public ClinicalTrials.gov benchmarks."}
    if space:
        cmd = ["databricks", "genie", "update-space", space, "--json", json.dumps(body), "-p", PROFILE, "-o", "json"]
    else:
        body["parent_path"] = "/Workspace/Users/karthiga.mahali@databricks.com/febar-trial-enrollment-risk"
        cmd = ["databricks", "genie", "create-space", "--json", json.dumps(body), "-p", PROFILE, "-o", "json"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    print(out.stdout[:2000] or out.stderr[:4000])
