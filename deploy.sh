#!/usr/bin/env bash
# One-shot deploy of ER แลกเวร onto a Google Sheet (default: the test copy)
# Usage: ./deploy.sh [SHEET_ID]
set -euo pipefail
cd "$(dirname "$0")"
SHEET_ID="${1:-1c5VlXDuZy2p1gxaRh2NnXXBDErAw9S6UzYtJvA5aQS4}"   # Copy of ตารางเวรstaff_ปี2569
CLASP="npx --yes @google/clasp"

[ -d node_modules ] || npm install --silent
$CLASP login --status >/dev/null 2>&1 || { echo "▶ clasp login (browser จะเปิด — เลือกบัญชีเจ้าของ Sheet)"; $CLASP login; }

if [ ! -f .clasp.json ]; then
  echo "▶ สร้าง bound script บน Sheet $SHEET_ID"
  $CLASP create --type sheets --parentId "$SHEET_ID" --title "ER แลกเวร" --rootDir .
fi
echo "▶ clasp push"; $CLASP push -f
echo "▶ clasp deploy (web app)"; $CLASP deploy --description "er-swap $(date +%F)" || true
echo
echo "▶ Deployments:"; $CLASP deployments
echo
cat <<MSG
ขั้นต่อไป (ครั้งเดียว ใน Apps Script editor → 'npx clasp open'):
  1. Run  setupAll        → อนุมัติ scope → log มี URL ของ Form
  2. Deploy ▸ Manage deployments ▸ ตรวจว่า Web app = Execute as Me / Anyone → copy URL .../exec
  3. Run  setWebAppUrl('https://script.google.com/macros/s/…/exec')
  4. (option) setAdminEmail('…')
แล้วเปิด URL นั้น = web app (login ด้วยอีเมลใน Roster)
MSG
