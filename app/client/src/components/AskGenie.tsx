import { useMemo } from 'react';
import {
  Alert, AlertDescription, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  Empty, EmptyDescription, EmptyHeader, EmptyTitle, GenieChatInput, GenieChatMessageList, useGenieChat,
} from '@databricks/appkit-ui/react';

const SUGGESTED = [
  'Which studies are Critical or High risk and why?',
  'What is the total projected delay cost by therapeutic area?',
  'Which at-risk studies have no intervention logged yet?',
  'Among public oncology Phase 3 trials, how often do biomarker-selected trials terminate for low accrual vs non-biomarker trials?',
];

export function AskGenie() {
  const { messages, status, error, sendMessage, reset } = useGenieChat({ alias: 'default' });
  const lastSql = useMemo(() => {
    for (const m of [...messages].reverse()) for (const a of m.attachments ?? []) if (a.query?.query) return a.query;
    return null;
  }, [messages]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <Card className="xl:col-span-2 flex flex-col h-[640px]">
        <CardHeader className="pb-2">
          <CardTitle>Ask the Meridian Trial Enrollment Risk agent</CardTitle>
          <CardDescription>
            Genie Agent over governed UC views and the portfolio metric view. Questions run on behalf of you (OBO), so your own Unity Catalog row-level (therapeutic area) and $ entitlements apply.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col min-h-0 gap-2">
          {messages.length === 0 ? (
            <Empty className="flex-1"><EmptyHeader><EmptyTitle>Ask about enrollment risk</EmptyTitle>
              <EmptyDescription>Try one of these:</EmptyDescription></EmptyHeader>
              <div className="flex flex-col gap-2 mt-2">{SUGGESTED.map((q) => (
                <Button key={q} variant="outline" size="sm" className="whitespace-normal text-left h-auto" onClick={() => sendMessage(q)}>{q}</Button>))}
              </div>
            </Empty>
          ) : (
            <GenieChatMessageList messages={messages} status={status} className="flex-1 min-h-0" />
          )}
          {status === 'streaming' && <p className="text-xs text-muted-foreground">Genie is analyzing your data…</p>}
          {status === 'error' && <Alert variant="destructive"><AlertDescription>{error ?? 'Genie failed. Rephrase or retry.'}</AlertDescription></Alert>}
          <GenieChatInput onSend={sendMessage} disabled={status === 'streaming'} placeholder="e.g. Which oncology studies are behind plan?" />
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">AI-generated from governed data via Genie. Check the generated SQL before acting on the answer.</p>
            {messages.length > 0 && <Button variant="ghost" size="sm" onClick={reset}>New conversation</Button>}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Generated SQL</CardTitle>
          <CardDescription>{lastSql?.title ?? lastSql?.description ?? 'How the last answer was computed'}</CardDescription>
        </CardHeader>
        <CardContent>
          {lastSql ? <pre className="overflow-auto text-xs whitespace-pre-wrap bg-muted p-3 rounded-md max-h-[480px]">{lastSql.query}</pre>
            : <p className="text-sm text-muted-foreground">Ask a question to see the SQL Genie ran.</p>}
          <div className="mt-3 flex flex-wrap gap-1">
            <Badge variant="outline">mv_portfolio_kpis</Badge><Badge variant="outline">v_portfolio_worklist</Badge>
            <Badge variant="outline">v_enrollment_weekly</Badge><Badge variant="outline">v_study_interventions</Badge><Badge variant="outline">v_trial_landscape</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
