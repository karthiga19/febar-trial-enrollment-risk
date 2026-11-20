// Cockpit API: operational reads/writes against Lakebase Postgres.
//  - worklist      -> Lakebase *synced table* (UC trial_risk_worklist -> Postgres, read-only)
//  - interventions -> Lakebase *native table* owned by the app (write-back), replicated back to UC by Lakehouse Sync
import { z } from 'zod';
import type { Application, Request } from 'express';

interface AppKitWithLakebase {
  lakebase: { query(text: string, params?: unknown[]): Promise<{ rows: Record<string, unknown>[] }> };
  server: { extend(fn: (app: Application) => void): void };
}

// Postgres location of the synced worklist (set in app.yaml; created by `databricks postgres create-synced-table`)
const WORKLIST = process.env.WORKLIST_TABLE ?? 'febar_trials.trial_risk_worklist_synced';
if (!/^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$/.test(WORKLIST)) throw new Error(`Invalid WORKLIST_TABLE: ${WORKLIST}`);

export const ACTIONS = ['add_sites', 'protocol_amendment', 'recruitment_campaign', 'site_remediation', 'monitor'] as const;

const SETUP_SQL = [
  `CREATE SCHEMA IF NOT EXISTS clinops`,
  `CREATE TABLE IF NOT EXISTS clinops.study_interventions (
     intervention_id   SERIAL PRIMARY KEY,
     study_code        TEXT NOT NULL,
     action_type       TEXT NOT NULL,
     notes             TEXT,
     status            TEXT NOT NULL DEFAULT 'open',
     risk_tier_at_log  TEXT,
     owner_email       TEXT NOT NULL,
     created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
     updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
   )`,
  // Lakehouse Sync (Lakebase -> UC CDC) requires full replica identity
  `ALTER TABLE clinops.study_interventions REPLICA IDENTITY FULL`,
  `CREATE INDEX IF NOT EXISTS idx_interventions_study ON clinops.study_interventions (study_code, created_at DESC)`,
];

const NewIntervention = z.object({
  action_type: z.enum(ACTIONS),
  notes: z.string().max(2000).optional().default(''),
});
const StatusUpdate = z.object({ status: z.enum(['open', 'in_progress', 'done', 'cancelled']) });

const userOf = (req: Request) => req.header('x-forwarded-email') ?? 'local-dev@meridian.example';

export async function setupCockpitRoutes(appkit: AppKitWithLakebase) {
  try {
    for (const stmt of SETUP_SQL) await appkit.lakebase.query(stmt);
    console.log('[cockpit] clinops.study_interventions ready');
  } catch (err) {
    console.warn('[cockpit] schema setup failed:', (err as Error).message);
  }

  appkit.server.extend((app) => {
    app.get('/api/whoami', (req, res) => {
      res.json({ email: req.header('x-forwarded-email') ?? null, user: req.header('x-forwarded-user') ?? null });
    });

    // Ranked worklist + latest logged intervention per study (one Postgres round-trip)
    app.get('/api/worklist', async (_req, res) => {
      try {
        const t0 = Date.now();
        const { rows } = await appkit.lakebase.query(`
          SELECT w.study_code, w.study_title, w.therapeutic_area, w.phase, w.indication, w.study_manager,
                 w.risk_tier, w.pct_of_plan, w.projected_delay_days, w.delay_cost_usd, w.addressable_savings_usd,
                 w.design_risk_percentile, w.recommended_action, w.headline, w.as_of_week, w.scored_at,
                 i.action_type AS last_action, i.status AS last_action_status, i.created_at AS last_action_at
          FROM ${WORKLIST} w
          LEFT JOIN LATERAL (
            SELECT action_type, status, created_at FROM clinops.study_interventions s
            WHERE s.study_code = w.study_code ORDER BY created_at DESC LIMIT 1) i ON TRUE
          ORDER BY CASE w.risk_tier WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Watch' THEN 3 ELSE 4 END,
                   w.delay_cost_usd DESC NULLS LAST`);
        res.set('x-lakebase-ms', String(Date.now() - t0)).json(rows);
      } catch (err) {
        console.error('worklist failed', err);
        res.status(500).json({ error: 'Failed to load worklist from Lakebase' });
      }
    });

    app.get('/api/studies/:code', async (req, res) => {
      try {
        const { rows } = await appkit.lakebase.query(`SELECT * FROM ${WORKLIST} WHERE study_code = $1`, [req.params.code]);
        if (!rows.length) { res.status(404).json({ error: 'Study not found' }); return; }
        res.json(rows[0]);
      } catch (err) {
        console.error('study failed', err);
        res.status(500).json({ error: 'Failed to load study' });
      }
    });

    app.get('/api/studies/:code/interventions', async (req, res) => {
      try {
        const { rows } = await appkit.lakebase.query(
          `SELECT * FROM clinops.study_interventions WHERE study_code = $1 ORDER BY created_at DESC`, [req.params.code]);
        res.json(rows);
      } catch (err) {
        console.error('interventions failed', err);
        res.status(500).json({ error: 'Failed to load interventions' });
      }
    });

    app.post('/api/studies/:code/interventions', async (req, res) => {
      const parsed = NewIntervention.safeParse(req.body);
      if (!parsed.success) { res.status(400).json({ error: 'Invalid intervention' }); return; }
      try {
        const { rows } = await appkit.lakebase.query(
          `INSERT INTO clinops.study_interventions (study_code, action_type, notes, risk_tier_at_log, owner_email)
           SELECT $1, $2, $3, w.risk_tier, $4 FROM ${WORKLIST} w WHERE w.study_code = $1
           RETURNING *`,
          [req.params.code, parsed.data.action_type, parsed.data.notes, userOf(req)]);
        if (!rows.length) { res.status(404).json({ error: 'Study not found' }); return; }
        res.status(201).json(rows[0]);
      } catch (err) {
        console.error('insert intervention failed', err);
        res.status(500).json({ error: 'Failed to log intervention' });
      }
    });

    app.patch('/api/interventions/:id', async (req, res) => {
      const parsed = StatusUpdate.safeParse(req.body);
      const id = Number.parseInt(req.params.id, 10);
      if (!parsed.success || Number.isNaN(id)) { res.status(400).json({ error: 'Invalid update' }); return; }
      try {
        const { rows } = await appkit.lakebase.query(
          `UPDATE clinops.study_interventions SET status = $1, updated_at = NOW() WHERE intervention_id = $2 RETURNING *`,
          [parsed.data.status, id]);
        if (!rows.length) { res.status(404).json({ error: 'Not found' }); return; }
        res.json(rows[0]);
      } catch (err) {
        console.error('update intervention failed', err);
        res.status(500).json({ error: 'Failed to update intervention' });
      }
    });
  });
}
