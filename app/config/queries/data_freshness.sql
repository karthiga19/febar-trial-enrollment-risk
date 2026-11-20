-- Provenance for every KPI: data week and model scoring time
SELECT max(as_of_week) AS as_of_week, max(scored_at) AS scored_at, count(*) AS studies
FROM km_catalog.febar_trials.v_portfolio_worklist
