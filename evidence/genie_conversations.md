# Genie Agent: Conversation API transcripts

Space `01f1e521658514a18b82a983c6fc8ec4` (Meridian Trial Enrollment Risk Agent). Each answer below is the Genie response, the SQL it generated, and the real rows returned.

## Q: Which studies are Critical or High risk and why?

**Status:** COMPLETED

**Genie's interpretation:** You want to see a list of studies that are classified as either Critical or High risk, along with details explaining why they are in these risk categories.

**Answer:** There are **9** studies currently flagged as **Critical** or **High** risk. Examples include:
- **MRD-ONC-204** (**Oncology**) — **Critical** because enrollment is at **51.1% of plan** with a projected delay of **730 days**; the headline points to **protocol complexity**.
- **MRD-ONC-213** (**Oncology**) — **Critical** because enrollment is at **38.4% of plan** with a projected delay of **730 days**.
- **MRD-ONC-210** (**Oncology**) — **Critical** because enrollment is at **8.7% of plan** with a projected delay of **730 days**; the headline also cites **protocol complexity**.
- **MRD-CVM-309** (**Cardiometabolic**) — **Critical** because enrollment is at **87.1% of plan** with a projected delay of **171 days**.
- **MRD-INF-323** (**Infectious Disease**) — **Critical** because enrollment is at **55.5% of plan** with a projected delay of **147 days**.
Across all 9 studies shown, the common pattern is that risk is being driven by being **behind plan**, **long projected delays**, and in several cases **protocol complexity** called out in the study headline.

```sql
SELECT `study_code`, `therapeutic_area`, `phase`, `risk_tier`, `pct_of_plan` * 100 AS `pct_of_plan`, `projected_delay_days`, `delay_cost_usd`, `design_risk_percentile`, `recommended_action`, `headline`
FROM `km_catalog`.`febar_trials`.`v_portfolio_worklist`
WHERE `risk_tier` IN ('Critical', 'High')
ORDER BY CASE `risk_tier` WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 ELSE 3 END ASC, `delay_cost_usd` DESC
```

| study_code | therapeutic_area | phase | risk_tier | pct_of_plan | projected_delay_days | delay_cost_usd | design_risk_percentile | recommended_action | headline |
|---|---|---|---|---|---|---|---|---|---|
| MRD-ONC-204 | Oncology | PHASE2 | Critical | 51.1 | 730 | 1.825E7 | 99.7 | protocol_amendment | MRD-ONC-204 Protocol Complexity Driving 2-Year Critical Enrollment Delay |
| MRD-ONC-213 | Oncology | PHASE2 | Critical | 38.4 | 730 | 1.825E7 | 9.5 | recruitment_campaign | MRD-ONC-213 Is 2 Years Behind Plan, Costing $18.25M |
| MRD-ONC-210 | Oncology | PHASE2 | Critical | 8.7 | 730 | 1.825E7 | 97.2 | site_remediation | MRD-ONC-210 Enrollment 91% Behind Plan; Protocol Complexity Driving 2-Year Delay |
| MRD-CVM-309 | Cardiometabolic | PHASE3 | Critical | 87.1 | 171 | 9405000.0 | 49.3 | add_sites | MRD-CVM-309 Enrollment 13% Behind Plan, 171-Day Delay Projected |
| MRD-INF-323 | Infectious Disease | PHASE3 | Critical | 55.50000000000001 | 147 | 8085000.0 | 52.9 | recruitment_campaign | MRD-INF-323 Enrollment 45% Behind Plan; 147-Day Delay Projected |
| MRD-IMM-224 | Immunology | PHASE2 | Critical | 59.0 | 299 | 7475000.0 | 89.7 | protocol_amendment | MRD-IMM-224 SLE Enrollment 41% Behind Plan; Protocol Driving Critical Delay |
| MRD-IMM-212 | Immunology | PHASE2 | Critical | 52.900000000000006 | 130 | 3250000.0 | 88.6 | protocol_amendment | MRD-IMM-212 Critical: Protocol Complexity Driving 130-Day LPI Slip |
| MRD-NEU-219 | Neuroscience | PHASE2 | High | 86.9 | 80 | 2000000.0 | 73.6 | protocol_amendment | MRD-NEU-219 Enrollment 13% Behind Plan; Protocol Amendment Required |
| MRD-IMM-221 | Immunology | PHASE2 | High | 77.9 | 64 | 1600000.0 | 36.0 | add_sites | MRD-IMM-221 Enrollment 22% Behind Plan; 64-Day Delay Projected |

## Q: What is the total projected delay cost by therapeutic area?

**Status:** COMPLETED

**Genie's interpretation:** You want to see the total projected delay cost broken down by therapeutic area, along with the number of studies at risk and the total number of studies in each therapeutic area.

**Answer:** The total projected delay cost is highest in **Oncology** at **$55.675M**, followed by **Immunology** at **$12.325M**, **Cardiometabolic** at **$9.405M**, **Infectious Disease** at **$8.085M**, and **Neuroscience** at **$2.0M**. Across these 5 therapeutic areas, **Oncology** is the clear outlier, with projected delay cost far above the rest.

```sql
SELECT `Therapeutic Area`, MEASURE(`Delay Cost USD`) AS `delay_cost_usd`, MEASURE(`At Risk Studies`) AS `at_risk_studies`, MEASURE(`Studies`) AS `studies` FROM `km_catalog`.`febar_trials`.`mv_portfolio_kpis` GROUP BY ALL ORDER BY `delay_cost_usd` DESC
```

| Therapeutic Area | delay_cost_usd | at_risk_studies | studies |
|---|---|---|---|
| Oncology | 5.5675E7 | 3 | 8 |
| Immunology | 1.2325E7 | 3 | 5 |
| Cardiometabolic | 9405000.0 | 1 | 4 |
| Infectious Disease | 8085000.0 | 1 | 3 |
| Neuroscience | 2000000.0 | 1 | 4 |

## Q: Which at-risk studies have no intervention logged yet?

**Status:** COMPLETED

**Genie's interpretation:** You want to see the list of studies that are currently at risk, specifically those classified as either Critical or High risk, and that do not have any interventions logged yet. The results include the study code, therapeutic area, risk tier, projected delay cost in USD, and the recommended action for each study. The list is ordered first by risk tier (Critical first, then High) and then by the delay cost in descending order.

**Answer:** There are **6 at-risk studies** with **no intervention logged** yet. Examples include:
- **MRD-ONC-204** (**Oncology**, **Critical**) — delay cost **$18.25M**; recommended action: **protocol amendment**
- **MRD-CVM-309** (**Cardiometabolic**, **Critical**) — delay cost **$9.41M**; recommended action: **add sites**
- **MRD-INF-323** (**Infectious Disease**, **Critical**) — delay cost **$8.09M**; recommended action: **recruitment campaign**
- **MRD-IMM-224** (**Immunology**, **Critical**) — delay cost **$7.48M**; recommended action: **protocol amendment**
- **MRD-IMM-212** (**Immunology**, **Critical**) — delay cost **$3.25M**; recommended action: **protocol amendment**

Most of these studies are **Critical** (5 of 6), with delay costs ranging from **$2.0M to $18.25M**.

```sql
SELECT `w`.`study_code`, `w`.`therapeutic_area`, `w`.`risk_tier`, `w`.`delay_cost_usd`, `w`.`recommended_action`
FROM `km_catalog`.`febar_trials`.`v_portfolio_worklist` `w`
WHERE `w`.`risk_tier` IN ('Critical', 'High')
  AND NOT EXISTS (
    SELECT 1
    FROM `km_catalog`.`febar_trials`.`v_study_interventions` `i`
    WHERE `i`.`study_code` = `w`.`study_code`
  )
ORDER BY CASE `w`.`risk_tier`
    WHEN 'Critical' THEN 1
    WHEN 'High' THEN 2
    WHEN 'Watch' THEN 3
    WHEN 'On track' THEN 4
    ELSE 5
  END ASC,
  `w`.`delay_cost_usd` DESC
```

| study_code | therapeutic_area | risk_tier | delay_cost_usd | recommended_action |
|---|---|---|---|---|
| MRD-ONC-204 | Oncology | Critical | 1.825E7 | protocol_amendment |
| MRD-CVM-309 | Cardiometabolic | Critical | 9405000.0 | add_sites |
| MRD-INF-323 | Infectious Disease | Critical | 8085000.0 | recruitment_campaign |
| MRD-IMM-224 | Immunology | Critical | 7475000.0 | protocol_amendment |
| MRD-IMM-212 | Immunology | Critical | 3250000.0 | protocol_amendment |
| MRD-NEU-219 | Neuroscience | High | 2000000.0 | protocol_amendment |

## Q: Show actual vs planned enrollment for MRD-CVM-309 over the last 8 weeks

**Status:** COMPLETED

**Genie's interpretation:** You want to see the actual cumulative enrollment versus the planned cumulative enrollment for the study MRD-CVM-309 over the last 8 weeks.

**Answer:** Would you prefer to see the data for the last 8 calendar weeks instead of the last 8 weeks with data available?

**Answer:** For **MRD-CVM-309**, actual enrollment was below plan in **all 8 weeks** shown, rising from **166 vs 188** on **2026-09-25** to **182 vs 209** on **2026-11-13**. The gap widened over this period from **22** participants to **27**, indicating the study fell further behind plan over the last 8 weeks.

Examples include:
- **2026-09-25:** **166 actual** vs **188 planned**
- **2026-10-09:** **172 actual** vs **194 planned**
- **2026-10-23:** **175 actual** vs **200 planned**
- **2026-11-06:** **180 actual** vs **206 planned**
- **2026-11-13:** **182 actual** vs **209 planned**

```sql
SELECT `week_ending`, `randomized_cum` AS `actual`, `planned_cum` AS `plan`
FROM `km_catalog`.`febar_trials`.`v_enrollment_weekly`
WHERE `study_code` = 'MRD-CVM-309'
  AND `week_ending` IS NOT NULL
  AND `week_ending` >= date_sub((SELECT MAX(`week_ending`) FROM `km_catalog`.`febar_trials`.`v_enrollment_weekly` WHERE `study_code` = 'MRD-CVM-309'), 49)
  AND `week_ending` <= (SELECT MAX(`week_ending`) FROM `km_catalog`.`febar_trials`.`v_enrollment_weekly` WHERE `study_code` = 'MRD-CVM-309')
ORDER BY `week_ending` ASC
```

| week_ending | actual | plan |
|---|---|---|
| 2026-09-25 | 166 | 188.0 |
| 2026-10-02 | 170 | 191.0 |
| 2026-10-09 | 172 | 194.0 |
| 2026-10-16 | 173 | 197.0 |
| 2026-10-23 | 175 | 200.0 |
| 2026-10-30 | 177 | 203.0 |
| 2026-11-06 | 180 | 206.0 |
| 2026-11-13 | 182 | 209.0 |

## Q: Among public oncology Phase 3 trials, how often do biomarker-selected trials terminate for low accrual vs non-biomarker trials?

**Status:** COMPLETED

**Genie's interpretation:** You want to see how often public oncology Phase 3 trials that require a biomarker terminate due to low patient accrual compared to those that do not require a biomarker.

**Answer:** In this **historical public oncology Phase 3/2/3 sample**, low-accrual termination was **18.75%** for **non-biomarker** trials (**128** trials) versus **16.03%** for **biomarker-selected** trials (**131** trials). In this sample, biomarker-selected trials terminated for low accrual **slightly less often** than non-biomarker trials.

```sql
SELECT
  `requires_biomarker`,
  COUNT(*) AS `trials`,
  100 * AVG(CAST(`terminated_for_low_accrual` AS INT)) AS `pct_low_accrual_in_sample`
FROM `km_catalog`.`febar_trials`.`v_trial_landscape`
WHERE `cohort` = 'historical'
  AND `therapeutic_area` ILIKE '%oncology%'
  AND `phase` IN ('PHASE3', 'PHASE2/3')
  AND `requires_biomarker` IS NOT NULL
GROUP BY `requires_biomarker`
ORDER BY `requires_biomarker` ASC
```

| requires_biomarker | trials | pct_low_accrual_in_sample |
|---|---|---|
| false | 128 | 18.75 |
| true | 131 | 16.030534351145036 |

## Q: How many studies are behind plan, and what is the total addressable savings if we act now?

**Status:** COMPLETED

**Genie's interpretation:** You want to know the total number of studies that are behind their enrollment plan and the total addressable savings in USD if actions are taken now, aggregated across the entire portfolio.

**Answer:** There are **11 studies** behind plan, and the total addressable savings if action is taken now is **$24,265,000**. Based on the single portfolio KPI result shown, that is the full current portfolio total for both measures.

```sql
SELECT MEASURE(`Behind Plan Studies`) AS `behind_plan_studies`, MEASURE(`Addressable Savings USD`) AS `addressable_savings_usd`
FROM `km_catalog`.`febar_trials`.`mv_portfolio_kpis`
GROUP BY ALL
```

| behind_plan_studies | addressable_savings_usd |
|---|---|
| 11 | 2.4265E7 |
