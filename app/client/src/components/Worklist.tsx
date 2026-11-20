import { useCallback, useEffect, useState } from 'react';
import {
  Alert, AlertDescription, Badge, Card, CardContent, CardDescription, CardHeader, CardTitle,
  Empty, EmptyDescription, EmptyHeader, EmptyTitle, Skeleton,
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@databricks/appkit-ui/react';
import { ACTION_LABEL, pct, usd, errorOf } from './format';
import { StudyDetail } from './StudyDetail';

export interface WorklistRow {
  study_code: string; study_title: string; therapeutic_area: string; phase: string; indication: string; study_manager: string;
  risk_tier: string; pct_of_plan: number; projected_delay_days: number; delay_cost_usd: number | null; addressable_savings_usd: number | null;
  design_risk_percentile: number; recommended_action: string; headline: string; as_of_week: string; scored_at: string;
  last_action: string | null; last_action_status: string | null; last_action_at: string | null;
}

export function TierBadge({ tier }: { tier: string }) {
  if (tier === 'Critical') return <Badge variant="destructive">Critical</Badge>;
  if (tier === 'High') return <Badge className="bg-warning text-warning-foreground">High</Badge>;
  if (tier === 'Watch') return <Badge variant="outline">Watch</Badge>;
  return <Badge variant="secondary" className="text-success">On track</Badge>;
}

export function Worklist() {
  const [rows, setRows] = useState<WorklistRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch('/api/worklist')
      .then(async (r) => {
        if (!r.ok) throw new Error(await errorOf(r));
        setLatency(r.headers.get('x-lakebase-ms'));
        return r.json() as Promise<WorklistRow[]>;
      })
      .then(setRows)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load worklist'));
  }, []);
  useEffect(load, [load]);

  if (error) return <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
      <Card className="xl:col-span-3">
        <CardHeader>
          <CardTitle>
            {rows ? `${rows.filter((r) => r.risk_tier === 'Critical' || r.risk_tier === 'High').length} studies need action this week` : 'Study worklist'}
          </CardTitle>
          <CardDescription>
            Ranked by risk tier, then $ at risk · served from Lakebase{latency ? ` in ${latency} ms` : ''} · click a study for the AI brief
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!rows && <div className="space-y-2">{['s1','s2','s3','s4','s5','s6','s7','s8'].map((k) => <Skeleton key={k} className="h-8 w-full" />)}</div>}
          {rows && rows.length === 0 && (
            <Empty><EmptyHeader><EmptyTitle>No studies visible</EmptyTitle>
              <EmptyDescription>Either the worklist has not been synced to Lakebase yet, or you are not entitled to any therapeutic area.</EmptyDescription></EmptyHeader></Empty>
          )}
          {rows && rows.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Study</TableHead><TableHead>Tier</TableHead><TableHead className="text-right">vs plan</TableHead>
                  <TableHead className="text-right">Delay</TableHead><TableHead className="text-right">$ at risk</TableHead>
                  <TableHead className="text-right">Design risk</TableHead><TableHead>AI recommends</TableHead><TableHead>Last action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.study_code} onClick={() => setSelected(r.study_code)}
                    className={`cursor-pointer ${selected === r.study_code ? 'bg-muted' : ''}`}>
                    <TableCell>
                      <div className="font-medium">{r.study_code}</div>
                      <div className="text-xs text-muted-foreground">{r.therapeutic_area} · {r.phase.replace('PHASE', 'Ph ')}</div>
                    </TableCell>
                    <TableCell><TierBadge tier={r.risk_tier} /></TableCell>
                    <TableCell className={`text-right ${Number(r.pct_of_plan) < 0.9 ? 'text-destructive' : ''}`}>{pct(r.pct_of_plan)}</TableCell>
                    <TableCell className="text-right">{r.projected_delay_days > 0 ? `${r.projected_delay_days}${r.projected_delay_days >= 730 ? '+' : ''} d` : '—'}</TableCell>
                    <TableCell className="text-right">{usd(r.delay_cost_usd)}</TableCell>
                    <TableCell className="text-right">{Number(r.design_risk_percentile).toFixed(0)}<span className="text-muted-foreground">th pct</span></TableCell>
                    <TableCell className="text-sm">{ACTION_LABEL[r.recommended_action] ?? r.recommended_action}</TableCell>
                    <TableCell className="text-xs">
                      {r.last_action ? <Badge variant="outline">{ACTION_LABEL[r.last_action] ?? r.last_action} · {r.last_action_status}</Badge>
                        : <span className="text-muted-foreground">none logged</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <div className="xl:col-span-2">
        {selected ? <StudyDetail studyCode={selected} onLogged={load} />
          : <Card><CardContent className="py-10">
              <Empty><EmptyHeader><EmptyTitle>Select a study</EmptyTitle>
                <EmptyDescription>See the GenAI brief, what drives its risk, enrollment vs plan, and log an intervention.</EmptyDescription></EmptyHeader></Empty>
            </CardContent></Card>}
      </div>
    </div>
  );
}
