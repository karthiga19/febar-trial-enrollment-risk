# Execution evidence: job run 1076184021196428

Job: `[dev karthiga_mahali] febar-trials-end-to-end`, result **SUCCESS**

Run page: https://fevm-serverless-stable-35goml.cloud.databricks.com/?o=7474650225234523#job/9221087271344/run/1076184021196428

| task | attempt | result | duration (s) | evidence |
|---|---|---|---|---|
| lakeflow_ingest_transform | 0 | SUCCESS | 63 | [pipeline_run.md](pipeline_run.md) |
| genai_enrichment | 0 | SUCCESS | 57 | [genai_enrichment.md](genai_enrichment.md) |
| retrain_gate | 0 | SUCCESS | 1 |  |
| train_model | 0 | SUCCESS | 87 | [train_model.md](train_model.md) |
| score_portfolio | 0 | SUCCESS | 127 | [score_portfolio.md](score_portfolio.md) |
| governance_semantic_layer | 0 | SUCCESS | 20 | SQL file `src/sql/05_governance_semantic_layer.sql` |
| sync_worklist_to_lakebase | 0 | SUCCESS | 42 | [pipeline_run.md](pipeline_run.md) |
