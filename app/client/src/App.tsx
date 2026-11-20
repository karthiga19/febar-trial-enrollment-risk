import { useEffect, useState } from 'react';
import {
  Badge,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  TooltipProvider,
  useAnalyticsQuery,
} from '@databricks/appkit-ui/react';
import { Activity } from 'lucide-react';
import { KpiRow } from './components/KpiRow';
import { Worklist } from './components/Worklist';
import { AskGenie } from './components/AskGenie';
import { DataJourney } from './components/DataJourney';

export default function App() {
  const [me, setMe] = useState<{ email: string | null } | null>(null);
  useEffect(() => {
    fetch('/api/whoami')
      .then((r) => (r.ok ? r.json() : null))
      .then(setMe)
      .catch(() => setMe(null));
  }, []);
  const { data: fresh } = useAnalyticsQuery('data_freshness', {});
  const f = fresh?.[0];

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-background">
        <header className="border-b px-6 py-3 flex flex-wrap items-center gap-3">
          <Activity className="h-5 w-5 text-primary" aria-hidden />
          <div>
            <h1 className="text-lg font-semibold text-foreground leading-tight">Trial Enrollment Risk Cockpit</h1>
            <p className="text-xs text-muted-foreground">Meridian Therapeutics · Clinical Operations (fictional sponsor)</p>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            {f && (
              <span>
                Enrollment data through week ending <b className="text-foreground">{String(f.as_of_week)}</b> · model scored{' '}
                {new Date(String(f.scored_at)).toLocaleString()}
              </span>
            )}
            <Badge variant="secondary">{me?.email ?? 'Signed in'}</Badge>
          </div>
        </header>

        <main className="p-6 space-y-6 max-w-[1400px] mx-auto">
          <KpiRow />
          <Tabs defaultValue="worklist">
            <TabsList>
              <TabsTrigger value="worklist">Study worklist</TabsTrigger>
              <TabsTrigger value="genie">Ask Genie</TabsTrigger>
              <TabsTrigger value="journey">How this works</TabsTrigger>
            </TabsList>
            <TabsContent value="worklist" className="mt-4">
              <Worklist />
            </TabsContent>
            <TabsContent value="genie" className="mt-4">
              <AskGenie />
            </TabsContent>
            <TabsContent value="journey" className="mt-4">
              <DataJourney />
            </TabsContent>
          </Tabs>
        </main>
      </div>
    </TooltipProvider>
  );
}
