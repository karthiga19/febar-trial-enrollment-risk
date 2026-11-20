#!/bin/bash
# Run SQL against the febar-trials Lakebase project as the current user (OAuth token as password).
# usage: tools/lakebase_sql.sh "SELECT 1"
EP=projects/febar-trials/branches/production/endpoints/primary
P=${PROFILE:-fevm-current}
HOST=$(databricks postgres get-endpoint $EP -p $P -o json | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['hosts']['host'])")
TOKEN=$(databricks postgres generate-database-credential $EP -p $P -o json | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
USER_=$(databricks current-user me -p $P -o json | python3 -c "import json,sys; print(json.load(sys.stdin)['userName'])")
PSQL=$(command -v psql || echo /opt/homebrew/opt/libpq/bin/psql)
PGPASSWORD="$TOKEN" "$PSQL" "host=$HOST user=$USER_ dbname=databricks_postgres sslmode=require" -v ON_ERROR_STOP=1 -c "$1"
