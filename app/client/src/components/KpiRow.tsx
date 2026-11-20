import { Alert, AlertDescription, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton, useAnalyticsQuery } from '@databricks/appkit-ui/react';
import { usd } from './format';

// KPI tiles from the governed UC metric view mv_portfolio_kpis (same definitions Genie uses).
export function KpiRow() {
  const { data, loading, error } = useAnalyticsQuery('portfolio_kpis', {});
  if (error) return <Alert variant="destructive"><AlertDescription>Could not load portfolio KPIs: {String(error)}</AlertDescription></Alert>;
  const k = data?.[0];
  const tiles = [
    { title: 'Studies at risk', value: k ? `${k.at_risk_studies} of ${k.studies}` : '', sub: 'Critical + High tier, active portfolio', tone: 'text-destructive' },
    { title: 'Studies behind plan', value: k ? `${k.behind_plan_studies} of ${k.studies}` : '', sub: 'Randomized to date < planned to date', tone: 'text-warning' },
    { title: 'Projected delay cost', value: k ? usd(k.delay_cost_usd) : '', sub: `${k ? Number(k.projected_delay_days).toLocaleString() : '—'} study-days late × direct cost/day`, tone: 'text-foreground' },
    { title: 'Addressable by acting now', value: k ? usd(k.addressable_savings_usd) : '', sub: '12 weeks earlier than quarterly review (assumption)', tone: 'text-primary' },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {tiles.map((t) => (
        <Card key={t.title}>
          <CardHeader className="pb-2">
            <CardDescription>{t.title}</CardDescription>
            <CardTitle className={`text-3xl ${t.tone}`}>{loading ? <Skeleton className="h-8 w-24" /> : t.value}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {t.sub}
            <div className="mt-1 opacity-70">Source: km_catalog.febar_trials.mv_portfolio_kpis</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
