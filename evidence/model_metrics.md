# Model evidence (MLflow, experiment `/Users/karthiga.mahali@databricks.com/febar_accrual_risk`)

Out-of-time evaluation: train on trials started ≤2017, test on 2018–2022. Population-weighted (case-control sampling undone).

| model | base_rate | roc_auc | pr_auc | top_decile_lift | top_decile_capture | top_decile_precision | brier |
|---|---|---|---|---|---|---|---|
| leakage_check_with_site_counts | 0.0444 | 0.7088 | 0.0942 | 2.6305 | 0.2615 | 0.1167 | 0.1049 |
| design_plus_genai | 0.0444 | 0.6747 | 0.0756 | 1.9844 | 0.1979 | 0.0881 | 0.1074 |
| design_only | 0.0444 | 0.6397 | 0.0706 | 1.5971 | 0.159 | 0.0709 | 0.1276 |


**Champion in Unity Catalog:** {"name": "km_catalog.febar_trials.accrual_risk_model", "version": "4", "run_id": "b73a8738c07e46dda4389b3b012c8cb7", "created": 1795209352206}


- `design_only`: protocol design fields only.
- `design_plus_genai` (**champion**): + GenAI eligibility-burden features.
- `leakage_check_with_site_counts`: adds CT.gov site/country counts, which partly encode the outcome. Excluded from the champion and shown only to quantify the inflation.


Full notebook output (SHAP importances, decile table): [train_model.md](train_model.md)
