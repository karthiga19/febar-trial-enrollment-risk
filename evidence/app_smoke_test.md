# Deployed app smoke test (Databricks App `febar-trial-risk`, AppKit)

URL: https://febar-trial-risk-7474650225234523.aws.databricksapps.com

| call | HTTP | latency (ms, incl. network) | result |
|---|---|---|---|
| GET /api/whoami | 200 | 147 | {'email': 'karthiga.mahali@databricks.com', 'user': '5803285627592048@7474650225234523'} |
| GET /api/worklist | 200 | 227 (Lakebase query 66 ms) | 24 studies; top 3: MRD-ONC-210 Critical $18,250,000; MRD-ONC-204 Critical $18,250,000; MRD-ONC-213 Critical $18,250,000 |
| GET /api/studies/MRD-IMM-221 | 200 | 128 | High: MRD-IMM-221 Trails Plan by 22%; 64-Day Delay Costs $1.6M |
| POST /api/studies/MRD-IMM-221/interventions | 201 | 142 | intervention_id=4 action=add_sites tier_at_log=High |
| PATCH /api/interventions/4 | 200 | 134 | status=in_progress |
