#!/usr/bin/env bash
# Print the variable block to paste into Railway → Variables → "Raw Editor" (service-account JSON inlined).
set -euo pipefail
cd "$(dirname "$0")/.."
SA=$(grep '^GOOGLE_SERVICE_ACCOUNT_JSON=' .env | cut -d= -f2-)
grep -vE '^(DATABASE_URL|GOOGLE_SERVICE_ACCOUNT_JSON|INTERNAL_CRON)=' .env | grep -v '^\s*$' | grep -v '^#'
echo "DATABASE_URL=sqlite:////data/agent.db"
echo "INTERNAL_CRON=true"
if [ -f "$SA" ]; then echo "GOOGLE_SERVICE_ACCOUNT_JSON=$(python3 -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1]))))" "$SA")"; else echo "GOOGLE_SERVICE_ACCOUNT_JSON=$SA"; fi
