import { useEffect, useMemo, useState } from 'react';
import {
  Alert, AlertDescription, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, LineChart,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Separator, Skeleton, Textarea,
} from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { ACTION_LABEL, num, pct, usd, errorOf } from './format';
import { TierBadge } from './Worklist';

interface Study {
  study_code: string; study_title: string; therapeutic_area: string; phase: string; study_manager: string; source_nct_id: string;
  target_enrollment: number; randomized_cum: number; planned_cum: number; pct_of_plan: number; active_sites: number; planned_sites: number;
  planned_lpi_date: string; projected_lpi_date: string; projected_delay_days: number; delay_cost_usd: number | null;
  design_risk_percentile: number; risk_drivers: string[] | string; top_restrictive_criteria: string[] | string; n_exclusion: number; complexity_score: number;
  risk_tier: string; recommended_action: string; headline: string; brief: string; action_rationale: string;
}
interface Intervention { intervention_id: number; action_type: string; notes: string; status: string; owner_email: string; created_at: string }

const asList = (v: string[] | string | null | undefined): string[] => {
  if (!v) return [];
  if (Array.isArray(v)) return v;
  try { const p: unknown = JSON.parse(v); return Array.isArray(p) ? p.map(String) : [String(v)]; } catch { return [String(v)]; }
};

export function StudyDetail({ studyCode, onLogged }: { studyCode: string; onLogged: () => void }) {
  const [study, setStudy] = useState<Study | null>(null);
  const [items, setItems] = useState<Intervention[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string>('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const params = useMemo(() => ({ study_code: sql.string(studyCode) }), [studyCode]);

  useEffect(() => {
    setStudy(null); setError(null);
    fetch(`/api/studies/${studyCode}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((s: Study) => { setStudy(s); setAction(s.recommended_action); })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load study'));
    fetch(`/api/studies/${studyCode}/interventions`).then((r) => (r.ok ? r.json() : [])).then(setItems).catch(() => setItems([]));
  }, [studyCode]);

  const logIntervention = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/studies/${studyCode}/interventions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action_type: action, notes }),
      });
      if (!r.ok) throw new Error(await errorOf(r));
      const created = (await r.json()) as Intervention;
      setItems((prev) => [created, ...prev]); setNotes(''); onLogged();
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to log'); } finally { setSaving(false); }
  };

  if (error) return <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>;
  if (!study) return <Card><CardContent className="space-y-3 py-6"><Skeleton className="h-6 w-2/3" /><Skeleton className="h-24 w-full" /><Skeleton className="h-48 w-full" /></CardContent></Card>;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2"><TierBadge tier={study.risk_tier} /><span className="text-sm text-muted-foreground">{study.study_code} · {study.study_manager}</span></div>
        <CardTitle className="text-lg">{study.headline}</CardTitle>
        <CardDescription>{study.study_title} · design template {study.source_nct_id} (ClinicalTrials.gov)</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border p-3 text-sm space-y-2">
          <div className="text-xs font-medium text-muted-foreground">AI study brief (Claude via Foundation Model API · verify against the numbers below)</div>
          <p>{study.brief}</p>
          <p><b>Recommended:</b> {ACTION_LABEL[study.recommended_action]} — {study.action_rationale}</p>
        </div>

        <div className="grid grid-cols-3 gap-3 text-sm">
          <div><div className="text-xs text-muted-foreground">Randomized / plan</div><div className="font-semibold">{num(study.randomized_cum)} / {num(study.planned_cum)} <span className="text-muted-foreground">({pct(study.pct_of_plan)})</span></div></div>
          <div><div className="text-xs text-muted-foreground">Projected LPI</div><div className="font-semibold">{String(study.projected_lpi_date)}</div><div className="text-xs text-muted-foreground">plan {String(study.planned_lpi_date)}</div></div>
          <div><div className="text-xs text-muted-foreground">Delay cost</div><div className="font-semibold">{usd(study.delay_cost_usd)}</div><div className="text-xs text-muted-foreground">{study.projected_delay_days} days</div></div>
          <div><div className="text-xs text-muted-foreground">Sites active</div><div className="font-semibold">{study.active_sites} / {study.planned_sites}</div></div>
          <div><div className="text-xs text-muted-foreground">Design risk</div><div className="font-semibold">{Number(study.design_risk_percentile).toFixed(0)}th pct</div><div className="text-xs text-muted-foreground">vs ~19K historical trials</div></div>
          <div><div className="text-xs text-muted-foreground">Eligibility</div><div className="font-semibold">{study.n_exclusion} exclusions</div><div className="text-xs text-muted-foreground">complexity {study.complexity_score}/10</div></div>
        </div>

        <div className="text-sm">
          <div className="text-xs font-medium text-muted-foreground mb-1">Why the model flags it (TreeSHAP drivers)</div>
          <div className="flex flex-wrap gap-1">{asList(study.risk_drivers).map((d) => <Badge key={d} variant="outline">{d}</Badge>)}</div>
          <div className="text-xs font-medium text-muted-foreground mt-2 mb-1">Most restrictive criteria (GenAI-extracted from the protocol)</div>
          <ul className="list-disc pl-5 text-sm">{asList(study.top_restrictive_criteria).map((c) => <li key={c}>{c}</li>)}</ul>
        </div>

        <div>
          <div className="text-xs font-medium text-muted-foreground">Cumulative randomizations — actual vs plan (SQL warehouse · v_enrollment_weekly)</div>
          <LineChart queryKey="enrollment_curve" parameters={params} xKey="week_ending" yKey={['actual', 'plan']} showSymbol={false} showLegend height={220} />
        </div>

        <Separator />
        <div className="space-y-2">
          <div className="text-sm font-medium">Log an intervention</div>
          <div className="flex gap-2">
            <Select value={action} onValueChange={setAction}>
              <SelectTrigger className="w-56"><SelectValue placeholder="Action" /></SelectTrigger>
              <SelectContent>{Object.entries(ACTION_LABEL).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
            </Select>
            <Button onClick={() => void logIntervention()} disabled={saving || !action}>{saving ? 'Saving…' : 'Log to Lakebase'}</Button>
          </div>
          <Textarea placeholder="Notes (e.g. 'Activate 6 backup sites in Spain and Poland; CRO to confirm by Dec 5')" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <div className="space-y-1">
            {items.length === 0 && <div className="text-xs text-muted-foreground">No interventions logged yet.</div>}
            {items.map((i) => (
              <div key={i.intervention_id} className="text-xs flex gap-2 items-center">
                <Badge variant="outline">{ACTION_LABEL[i.action_type] ?? i.action_type}</Badge>
                <span>{i.notes}</span>
                <span className="ml-auto text-muted-foreground">{i.owner_email} · {new Date(i.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
          <div className="text-xs text-muted-foreground">Written to Lakebase table clinops.study_interventions → replicated to Unity Catalog by Lakehouse Sync → visible to Genie.</div>
        </div>
      </CardContent>
    </Card>
  );
}
