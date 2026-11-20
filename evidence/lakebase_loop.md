# Lakebase evidence: operational serving and the closed loop

## 1. UC → Lakebase synced table (`km_catalog.febar_trials.trial_risk_worklist_synced`, TRIGGERED, refreshed by the job's `sync_worklist_to_lakebase` task)

```json
{
 "status": {
  "detailed_state": "SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE",
  "last_sync": {
   "delta_table_sync_info": {
    "delta_commit_time": "2026-11-20T20:54:53.168Z",
    "delta_commit_version": 5
   },
   "sync_end_time": "2026-11-20T20:55:59.249430Z",
   "sync_start_time": "2026-11-20T20:55:58.378578Z"
  },
  "message": "Synced table creation succeeded using Delta Live Tables: https://fevm-serverless-stable-35goml.cloud.databricks.com#joblist/pipelines/e3b8a95f-9ff7-4416-98fe-85c6934143f2/updates/50e8a634-793a-43b7-99a3-af4646d9bf75.",
  "pipeline_id": "e3b8a95f-9ff7-4416-98fe-85c6934143f2"
 },
 "spec": null
}
```

## 2. Postgres read path (psql against the Lakebase endpoint)

```text
risk_tier | count 
-----------+-------
 Critical  |     7
 High      |     2
 On track  |     5
 Watch     |    10
(4 rows)

                                                                                             QUERY PLAN                                                                                             
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Index Scan using "__db_tmp_aca037ad-f5b4-4b2e-9bb0-2af421271c22_pkey" on partition_16995 trial_risk_worklist_synced  (cost=0.14..8.16 rows=1 width=1446) (actual time=0.004..0.004 rows=1 loops=1)
   Index Cond: (study_code = 'MRD-CVM-309'::text)
 Planning Time: 0.272 ms
 Execution Time: 0.889 ms
(4 rows)
```

## 3. App write-back → Lakebase native table → Lakehouse Sync → UC (SCD history)

The app logged intervention 4 and then updated its status to `in_progress`. Lakehouse Sync replicated both changes to UC within ~22s:

| _pg_change_type | _timestamp | action_type | intervention_id | status | study_code |
|---|---|---|---|---|---|
| insert | 2026-11-20T20:58:03.864 | add_sites | 4 | open | MRD-IMM-221 |
| update_preimage | 2026-11-20T20:58:03.997 | add_sites | 4 | open | MRD-IMM-221 |
| update_postimage | 2026-11-20T20:58:03.997 | add_sites | 4 | in_progress | MRD-IMM-221 |


**Current state view used by Genie (v_study_interventions)**
```sql
SELECT intervention_id, study_code, action_type, status, risk_tier_at_log, owner_email, created_at FROM km_catalog.febar_trials.v_study_interventions ORDER BY intervention_id
```
| action_type | created_at | intervention_id | owner_email | risk_tier_at_log | status | study_code |
|---|---|---|---|---|---|---|
| protocol_amendment | 2026-11-20T20:30:25.694Z | 1 | karthiga.mahali@databricks.com | Critical | open | MRD-ONC-210 |
| add_sites | 2026-11-20T20:30:25.844Z | 2 | karthiga.mahali@databricks.com | Critical | open | MRD-ONC-213 |
| add_sites | 2026-11-20T20:56:57.223Z | 3 | karthiga.mahali@databricks.com | High | in_progress | MRD-IMM-221 |
| add_sites | 2026-11-20T20:58:03.861Z | 4 | karthiga.mahali@databricks.com | High | in_progress | MRD-IMM-221 |

