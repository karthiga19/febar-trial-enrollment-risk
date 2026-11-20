# Demo script: tell, show, tell (about 12 minutes)

**Audience:** Dana Whitfield, VP Clinical Operations (exec sponsor), and Priya Raman, Clinical Trial Manager (domain owner). The technical persona is the R&D Data Platform Lead.
**Hero pair (two late studies, two different fixes):**
- **MRD-IMM-224** (lupus, Ph 2): 59% of plan, 299 days late, **$7.5M**, design risk in the **90th** percentile (28 exclusions, ANA + anti-dsDNA + anti-Sm required). Playbook: **protocol amendment**.
- **MRD-CVM-309** (pediatric obesity, Ph 3): 87% of plan, 171 days late, **$9.4M**, design risk in the **49th** percentile. Playbook: **add sites**.

## Before the demo (5 min)
1. Open the app: https://febar-trial-risk-7474650225234523.aws.databricksapps.com, Study worklist tab.
2. To show the **live file drop**, unpause the file-arrival trigger. Dev-mode bundles keep it paused, and this lasts until the next deploy:
   `databricks jobs update --json '{"job_id": 9221087271344, "new_settings": {"trigger": {"pause_status": "UNPAUSED", "file_arrival": {"url": "/Volumes/km_catalog/febar_trials/raw/meridian/enrollment/", "min_time_between_triggers_seconds": 60}}}}' -p fevm-current`
3. Have the Genie tab and Catalog Explorer (`km_catalog.febar_trials`, Lineage tab on `trial_risk_worklist`) open in other tabs.

## TELL (90 s): the problem in their KPIs
> "Dana, 8 in 10 trials miss enrollment timelines, and you usually find out at the quarterly review. Each month a Phase 3 slips costs about $1.6M in direct cost, and much more in lost exclusivity at launch. Today you'll see how Meridian finds the at-risk studies **weeks earlier**, knows **why**, and acts, all on one governed platform."

## SHOW (8 min)
1. **KPI row (30 s).** "9 of 24 studies need action. $87.5M of projected direct delay cost, $24.3M of it addressable if we act 12 weeks earlier. Every number comes from one governed metric view. Genie uses the same definitions."
2. **Worklist → MRD-IMM-224 (90 s).**
   - Read the AI brief out loud. Point at the *numbers it cites*. "Priya would spend about 2 hours a month per study writing this."
   - "**Why**: the model is trained on 12 years of *real* ClinicalTrials.gov outcomes. This protocol is riskier than 90% of industry trials, because GenAI read its 28 exclusion criteria and found triple-autoantibody confirmation plus broad comorbidity exclusions. The playbook says **amend the protocol**. Adding sites won't fix eligibility."
3. **Contrast with MRD-CVM-309 (45 s).** "Also late, and it costs more, but the design risk is ordinary (49th percentile) and 16 of 17 sites are active. This is a *capacity* problem, so: **add sites**. A CTMS shows both as 'behind plan'. Only design risk plus operational risk tells you they need different fixes."
4. **Log the intervention on MRD-CVM-309 (1 min).** Keep *Add sites* and type a note. "That went to Lakebase, the operational database behind the app. Within seconds Lakehouse Sync streams it back into Unity Catalog."
5. **Genie (2 min).** Ask *"Which at-risk studies have no intervention logged yet?"* MRD-CVM-309 is now **gone** from the list. Open the generated SQL. "It runs *as you*. An oncology lead would only see oncology studies, and no dollar figures."
6. **Lineage (1 min, for the technical persona).** Catalog Explorer → `trial_risk_worklist` → Lineage: raw API files → pipeline → model → worklist → synced table.
7. **Optional live drop (1 min).** `databricks fs cp data/meridian_holdback/enrollment/edc_enrollment_week_2026-11-20.csv dbfs:/Volumes/km_catalog/febar_trials/raw/meridian/enrollment/ -p fevm-current`. The job triggers by itself, and the worklist refreshes in about 15 minutes.

## TELL (90 s): value and next step
> "Three things: you see risk **before first patient in**, not after; every recommendation is **explained** and auditable; and the loop closes, so what your team does is measured and becomes training data. Next step: a 6-week pilot on 10 live studies with your CTMS/EDC feeds. Success means flagging each at-risk study at least 8 weeks before your current process does."

---

## Objection handling

### Business persona (VP Clinical Ops)
| Objection | Answer |
|---|---|
| "Our CTMS already shows actual vs plan." | It shows you're late *after* you're late. The design-risk score exists on day 1 and explains *why*. The CTMS has no model of what makes protocols fail. |
| "How do I trust a $24M number?" | It's direct cost only. The ~$500K/day lost-sales upside is excluded on purpose. Assumptions sit in a finance-owned table: change $55K/day to your number and every tile updates. |
| "The AI could hallucinate a recommendation." | The AI doesn't pick the action. A deterministic, auditable playbook does (SQL rules your study leads can edit). The LLM only writes the explanation, using only the facts passed in, and the numbers sit next to it. |
| "How accurate is the model?" | Out-of-time test on 2018–2022 trials: ROC-AUC 0.67, and the top decile fails at 2.0× the base rate. I removed a leaky feature that made it *look* better (0.71). It's a **prioritization** tool, not an oracle, and it is paired with the operational signal. Calibrating on your own history is pilot weeks 3–4. |
| "My team won't use another tool." | It's one screen and one click to log an action. Genie answers ad-hoc questions in plain English, and it can sit in Slack or Teams. |

### Technical persona (R&D data platform lead)
| Objection | Answer |
|---|---|
| "Why not just query the warehouse from the app?" | The app is operational: row lookups many times a day plus transactional writes. Lakebase serves the worklist in ~6 ms and gives ACID writes. The warehouse handles the aggregates. |
| "How do you keep Postgres and the lakehouse consistent?" | UC is the source of truth. The synced table reads the Delta change feed (the worklist is MERGEd, never replaced). Interventions flow back through Lakehouse Sync CDC into an SCD-2 history table. No custom ETL. |
| "Governance across Genie, app and BI?" | Consumers only see governed views. Row security by therapeutic area and $ masking live in one entitlement table plus 2 UDFs. Genie runs OBO, so each user's own rights apply. The app SP has SELECT on views only. |
| "LLM cost at scale?" | Enrichment is incremental (anti-join): only new trials go to the model. Bulk calls use Haiku. Sonnet only writes the 24 briefs. The weekly re-run costs cents. |
| "Data leakage in the model?" | Actual enrollment, completion dates and status are never features. The split is out-of-time. Case-control sampling is re-weighted so the metrics describe the real population. |
| "Is ClinicalTrials.gov data clean enough?" | Bronze keeps the raw record as VARIANT. Silver applies expectations (valid NCT ID, phase, eligibility present), and violations are visible in the pipeline event log. |
