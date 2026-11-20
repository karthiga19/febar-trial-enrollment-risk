-- Portfolio KPIs from the governed UC metric view (same definitions Genie uses)
SELECT
  MEASURE(`Studies`)                 AS studies,
  MEASURE(`At Risk Studies`)         AS at_risk_studies,
  MEASURE(`Behind Plan Studies`)     AS behind_plan_studies,
  MEASURE(`Projected Delay Days`)    AS projected_delay_days,
  MEASURE(`Delay Cost USD`)          AS delay_cost_usd,
  MEASURE(`Addressable Savings USD`) AS addressable_savings_usd
FROM km_catalog.febar_trials.mv_portfolio_kpis
