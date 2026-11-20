# Catch the trial that will miss enrollment *before* it costs you $18M
### Trial Enrollment Risk Cockpit · Meridian Therapeutics · Clinical Operations
Built on Databricks: Lakeflow · Unity Catalog · Lakebase · GenAI + ML · Genie · Databricks Apps

---

## 1. The problem, in your KPIs

- **~80% of trials miss enrollment timelines.** Low accrual is one of the most common reasons a trial is terminated.
- **Every day late costs money:** ~**$55K/day** in direct cost for a Phase 3 (sites, CRO, monitoring), ~$25K for a Phase 2. On top of that, ~**$500K/day** in lost exclusivity once the asset launches.
- **You find out too late.** Actual-vs-plan sits in the CTMS, but the *portfolio decision* happens at the quarterly review. By then the cheap fixes (add sites early, amend before 30 sites are trained) have passed.
- **Nobody can say *why*.** The protocol, the sites and recruitment get blamed in turn. The fix depends on which one it is.

> **Dana (VP Clinical Ops):** "Which of my 24 studies will be late, how much will it cost, and what should we do *this week*?"
> **Priya (Clinical Trial Manager):** "Tell me why my study is struggling and what to do, without two hours of status prep."

---

## 2. The outcome: what Meridian sees today (from the live build)

| KPI | Value |
|---|---|
| Studies needing action this week | **9 of 24** (7 Critical, 2 High) |
| Studies behind plan | **11 of 24** |
| Projected enrollment delay | **3,118 study-days** |
| Projected **direct** cost of delay | **$87.5M** |
| **Addressable by acting 12 weeks earlier than the quarterly review** | **$24.3M** |

- **Exec sponsor value:** $24M of direct cost addressable on *today's* portfolio. The headline excludes the lost-sales upside.
- **Domain owner value:** a defensible brief per study in seconds (~2 h/study/month of status prep saved, ≈ **570 hours a year** across 24 studies), plus one place to log and track the fix.

---

## 3. A conservative value model you can change yourself

Assumptions live in a Unity Catalog table owned by Clinical Finance (`value_assumptions`). Change them and every number updates.

| Addressable direct cost on today's portfolio | detect 4 wks earlier | 8 wks | **12 wks** |
|---|---|---|---|
| Low cost case ($40K/day Ph3, $18K/day Ph2) | $6.3M | $12.2M | $17.5M |
| **Base case ($55K/day Ph3, $25K/day Ph2)** | $8.7M | $16.9M | **$24.3M** |

- **Excluded on purpose:** lost exclusivity (~$500K/day per Phase 3 asset). One rescued Phase 3 month would be worth ~$15M more.
- **Platform cost:** serverless pipeline + ~30K one-time LLM calls; incremental weekly runs cost cents.

---

## 4. What the study team does with it (the 2-minute workflow)

1. **Open the worklist.** Studies are ranked by risk tier and $ at risk, served from Lakebase in milliseconds.
2. **Read the brief.** It is written by GenAI and cites the numbers: *"SLE study at 59% of plan, 299 days late, $7.5M at risk; 28 exclusion criteria, design risk in the 90th percentile vs. historical trials…"*
3. **See *why*.** The model's top drivers, the most restrictive eligibility criteria (extracted by GenAI from the protocol), and the actual-vs-plan curve.
4. **Act.** Log *Protocol amendment / Add sites / Recruitment campaign*. It is written to Lakebase and streamed back to the lakehouse in seconds.
5. **Ask.** *"Which at-risk studies have no intervention logged yet?"* The Genie Agent answers in plain English, runs **as you**, and shows its SQL.

---

## 5. Two late studies, two different fixes

| | **MRD-IMM-224** (lupus, Phase 2) | **MRD-CVM-309** (pediatric obesity, Phase 3) |
|---|---|---|
| Enrollment vs plan | 59% | 87% |
| Projected delay / cost | 299 days / **$7.5M** | 171 days / **$9.4M** |
| Design risk vs historical trials | **90th percentile**: 28 exclusions, mandatory ANA + anti-dsDNA + anti-Sm confirmation | **49th percentile**: the protocol is ordinary |
| Diagnosis | **The protocol is the bottleneck** | **Site capacity is the bottleneck** |
| Playbook action | **Protocol amendment** | **Add sites** |

A CTMS shows both studies as "behind plan". Only the combination of an **ML design-risk score and the operational signal** tells you they need *different* fixes.

---

## 6. Why you can trust it

- **Real evidence base:** 49,677 public ClinicalTrials.gov trials. GenAI read **7,921 free-text termination reasons** to build the label (2,790 terminated for low accrual), and **4,800 eligibility sections** to measure protocol burden.
- **Honest validation:** trained on trials started ≤2017, tested on 2018–2022 (out-of-time). Trials in the top risk decile fail for low accrual at **2.0× the base rate**.
- **GenAI value measured, not assumed:** adding the GenAI eligibility features raises ROC-AUC from **0.64 to 0.67** and top-decile lift from **1.6× to 2.0×**.
- **Leakage removed:** site counts on ClinicalTrials.gov partly encode the outcome. Including them would have *looked* better (AUC 0.71), so they were excluded.
- **Policy decides, AI explains:** the recommended lever comes from an explicit clinical-ops playbook. GenAI writes the explanation and may only use the facts it is given.
- **Governed end to end:** one copy of the data, row-level security by therapeutic area, $ figures masked for non-finance users, full lineage.

---

## 7. One platform, one loop

```
ClinicalTrials.gov API + CTMS/EDC files ─▶ Lakeflow (Auto Loader, bronze→silver→gold, quality rules)
   ─▶ GenAI (ai_query: termination reasons → label, eligibility → features, study briefs)
   ─▶ ML (LightGBM in Unity Catalog, explained per study)
   ─▶ Unity Catalog (tags, row/column security, metric view, lineage)
   ─▶ Lakebase (worklist served in ms; interventions written back)  ──Lakehouse Sync──▶ back to UC
   ─▶ Genie Agent (plain-English questions, runs as the user) ─▶ Databricks App (the cockpit)
```

- **One job, one schedule.** A new weekly EDC file landing triggers the whole chain.
- **No extra tools to integrate.** No separate ETL tool, feature store, vector database, BI server or OLTP database.

---

## 8. Key decisions and trade-offs

| Choice | Instead of | Because |
|---|---|---|
| Design risk + operational risk | Actual-vs-plan only | Know *before* first patient in, and know *why* |
| Label = terminated *for low accrual* (GenAI-classified) | Any termination | Most industry terminations are business decisions, not enrollment failures |
| Lakebase for the worklist + write-back | App querying the warehouse | Operational reads in ms, ACID writes, closed loop via Lakehouse Sync |
| Deterministic playbook + GenAI explanation | Letting the LLM pick the action | Auditable, consistent decisions; the AI explains, it doesn't decide |
| Direct cost only in the headline | Including lost sales | A number the CFO will accept |

---

## 9. Proposed next step: a 6-week pilot

| Week | Milestone |
|---|---|
| 1–2 | Connect your CTMS + EDC extracts (Lakeflow Connect / file drop); map 10 live studies |
| 3–4 | Calibrate the model on your own historical studies; tune the playbook with your study leads |
| 5–6 | Study teams use the cockpit weekly; Genie Agent in Teams/Slack |

**Success criteria:** flag each at-risk study **≥ 8 weeks earlier** than the current review; **≥ 80%** of study managers log interventions in the tool; finance signs off the value model.

---

## Appendix A: model results (out-of-time test, 2018–2022, population-weighted)

| Model | ROC-AUC | PR-AUC | Top-decile lift | Failures caught in top 10% |
|---|---|---|---|---|
| Design only | 0.640 | 0.071 | 1.60× | 15.9% |
| **Design + GenAI (champion)** | **0.675** | **0.076** | **1.98×** | **19.8%** |
| + site counts (leaky, excluded) | 0.709 | 0.094 | 2.63× | 26.2% |

Base rate: 4.4% of industry Phase 2/3 trials (2018–2022 starts) terminated for low accrual.

## Appendix B: data and privacy

Public data: ClinicalTrials.gov API v2. Synthetic: Meridian Therapeutics and its study codes, managers, sites and enrollment (designs templated from real recruiting trials). No customer data.
