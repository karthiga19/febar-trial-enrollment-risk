import { createApp, analytics, genie, lakebase, server } from '@databricks/appkit';
import { setupCockpitRoutes } from './routes/cockpit-routes';

await createApp({
  plugins: [
    analytics(),
    lakebase(),
    // Genie Agent "Meridian Trial Enrollment Risk Agent"; space id injected from the app's genie-space resource
    genie({ spaces: { default: process.env.DATABRICKS_GENIE_SPACE_ID ?? '' } }),
    server(),
  ],
  async onPluginsReady(appkit) {
    await setupCockpitRoutes(appkit);
  },
});
