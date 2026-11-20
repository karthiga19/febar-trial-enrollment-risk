import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@databricks/appkit-ui/react';

const STEPS = [
  ['1 · Lakeflow', 'Auto Loader ingests raw ClinicalTrials.gov API pages (~50K trials, public) and the sponsor\'s weekly EDC/CTMS files into bronze → silver → gold, with data-quality expectations. A file-arrival trigger runs the job when a new weekly enrollment file lands.'],
  ['2 · Unity Catalog', 'Every table, view, function, metric view and the ML model is governed in km_catalog.febar_trials. Tags separate public from confidential data, row/column security by therapeutic area and $ entitlement, and lineage is captured end to end.'],
  ['3 · GenAI', 'ai_query (Claude) classifies ~7.9K free-text "why stopped" reasons into the low-accrual label and extracts structured eligibility burden from ~4.8K protocols. It also writes the study brief you read in the worklist.'],
  ['4 · ML', 'A LightGBM model (UC: accrual_risk_model@champion) predicts the risk of low-accrual termination from protocol design. It is out-of-time validated, and TreeSHAP explains each study\'s risk.'],
  ['5 · Lakebase', 'The scored worklist syncs from UC into Lakebase Postgres for fast operational reads. Interventions are written to a native Lakebase table, and Lakehouse Sync streams them back to UC.'],
  ['6 · Genie + App', 'This AppKit app serves study managers. The embedded Genie Agent answers ad-hoc questions over the same governed views and metric view.'],
];

export function DataJourney() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>One governed loop: raw public data to a decision and back</CardTitle>
        <CardDescription>Everything on this screen comes from one Databricks pipeline. Nothing is stitched together.</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {STEPS.map(([t, d]) => (
          <div key={t} className="rounded-md border p-3"><div className="font-medium text-sm text-primary">{t}</div><p className="text-sm text-muted-foreground mt-1">{d}</p></div>
        ))}
      </CardContent>
    </Card>
  );
}
