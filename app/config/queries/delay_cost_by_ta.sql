-- Projected delay cost by therapeutic area (governed metric view)
SELECT `Therapeutic Area` AS therapeutic_area,
       MEASURE(`Delay Cost USD`) AS delay_cost_usd,
       MEASURE(`At Risk Studies`) AS at_risk_studies
FROM km_catalog.febar_trials.mv_portfolio_kpis
GROUP BY ALL
ORDER BY delay_cost_usd DESC
