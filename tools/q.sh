#!/bin/bash
# usage: tools/q.sh "SQL"  -> prints a TSV table (header + rows)
databricks experimental aitools tools query "$1" -p ${PROFILE:-fevm-current} 2>/dev/null | python3 -c '
import json,sys
raw=sys.stdin.read(); i=raw.find("[")
rows=json.loads(raw[i:]) if i>=0 else []
if not rows: print(raw[:2000]); sys.exit()
cols=list(rows[0].keys())
print("\t".join(cols))
for r in rows: print("\t".join(str(r.get(c)) for c in cols))'
