# LINE Shift-Swap Agent (MVP)

Nurses report swaps as free text in the ward LINE group → bot extracts (OpenAI Structured Outputs) → checks the roster
(Google Sheet) → reporter confirms → bot writes the cells + audit row. See [PLAN.md](PLAN.md) for the full spec.

## Setup

### 1. Google Sheet (one per ward)
- Create the spreadsheet with a **CareSync-controlled Google account as owner** (owners bypass protected ranges; head
  nurse must only be *Editor* so protection is enforceable — PLAN §4/§15).
- Share **Editor** to the service account email (`client_email` in the JSON) and to the head nurse.
- Seed tabs: `python scripts/seed_sheet.py <SPREADSHEET_ID> 2569-10` creates `_control`, `_staff`, `_audit` and a demo
  `2569-10` tab (draft). Fill `_staff` with real names + nicknames.

### 2. LINE OA
- Create an OA named after the ward, enable **Allow bot to join group chats**, disable auto-reply/greeting.
- Messaging API: copy channel secret + long-lived access token; set webhook URL `https://<host>/webhook`.
- Invite the OA into the ward group. Send any message; read the `groupId` (`C…`) from the webhook log and put it in
  `LINE_ALLOWED_GROUP_IDS` and `SHEET_ID_MAP=<groupId>:<spreadsheetId>`.
- Head nurse: read their `userId` (`U…`) from the log → `HEAD_NURSE_LINE_IDS`. No onboarding for other nurses.

### 3. Run locally
```sh
uv venv && uv pip install -e ".[dev]"
cp .env.example .env   # fill in
uvicorn agent.main:app --reload --port 8080 --app-dir src
ngrok http 8080        # put https://xxx.ngrok.app/webhook in LINE console
pytest
```

### 4. Deploy (Cloud Run)
```sh
gcloud run deploy line-swap-agent --source . --region asia-southeast1 --set-env-vars "$(paste -sd, .env)"
```
Cron (Cloud Scheduler, POST with `?token=$CRON_TOKEN`): `/cron/expire` every 10 min, `/cron/drift` every 30 min,
`/cron/go-live` daily 00:05 Asia/Bangkok.

Start with `DRY_RUN=true` for a 1-week shadow run: the bot replies normally but logs intended writes instead of
touching the Sheet.

## Roster layouts (`ROSTER_LAYOUT`)
- `table` — PLAN §4: `staff_id | name | 1…31`, cells hold codes `ช/บ/ด/conference` (multi-code cells like `ชบ` ok).
- `grid` — the existing ER attending sheet (`ตารางเวรstaff_ปี2569`): one tab per Thai month (`กันยายน2569`, revision
  tabs `กันยายน2569 (แลกN)` → the **rightmost** matching tab is used), week blocks with `วันที่` rows, names in cells.
  Row → code mapping lives in `config/shifts.yaml` `grid_rows` (`8.00 - 16.00` + `On floor 1-2` = ช, `16.00 - 24.00` = บ,
  `0.00 - 8.00` = ด, conference rows = conference). Identity = name as written in the cell (`_staff` optional; if present
  it only supplies nicknames). A swap replaces the name in the slot (`' TM'` suffix preserved); an edit moves the name to
  a free slot of the target row or rejects when none is free. `_planned`/`_diff`/`_audit`/`_control` work the same;
  `ประกาศตาราง 2569-09` resolves to the September tab. **This deviates from PLAN §4 by owner request** (bot bound to the
  real sheet instead of re-entering it in the table schema).

## Monthly cycle (head nurse, in the group)
| Command | Effect |
|---|---|
| `ตรวจตาราง 2569-10` | parse report: unknown codes / staff, empty rows |
| `ประกาศตาราง 2569-10` | snapshot `_planned`, protect tab (service account sole editor), status=published, post link |
| `ปิดตาราง 2569-09` | status=closed, build `_diff`, reply per-person delta |
| `สถานะ` / `ยกเลิก` | anyone: own pending change |
| `ตาราง` / `ตารางเวร` / `ขอตารางเวร [เดือน]` | anyone: link to the month tab (default current month; `เดือนหน้า` ok) |

Month accepted as `2569-10`, `10/2569`, `ต.ค.`, `ตุลาคม`, `ต.ค. 69`.

## Daily
"แลกเวรดึก 3 ต.ค. ของศรี กับ เช้า 5 ต.ค. ของบี" → summary + [ยืนยัน] [ยกเลิก] (Quick Reply; typing ยืนยัน/ยกเลิก also
works). Only the reporter can confirm; 2 h TTL. Mismatch → reply shows the real roster value, no buttons.
Whole-day swap: "แลกทั้งวัน 3 ต.ค. ของศรี กับ 5 ต.ค. ของบี" / "ศรีแลกวันที่ 3 กับบีวันที่ 5" moves every shift each person holds that day in one request.
Rule: `conference` is exchanged only with another `conference` slot (no give, no mixing with ช/บ/ด).
Head nurse single-cell edit: "เปลี่ยนพี่ศรี วันที่ 5 เป็นดึก", "บี วันที่ 12 หยุด".

## PDPA notes
Only group messages classified as swap/edit are stored. LINE userIds live only in `HEAD_NURSE_LINE_IDS` and on open
requests (nulled on any terminal state). Audit stores the reporter's display name. No LINE identifiers or names are
sent to OpenAI beyond the message text itself.

## Layout
`src/agent/` — `main.py` (FastAPI) · `line/` · `llm/` · `sheets/` · `change/` (state machine, checks, service) ·
`commands/` · `thai_date.py` · `shifts.py` · `db.py`. Tests in `tests/` (gspread + OpenAI mocked; fixtures in
`prompts/extract_examples.jsonl`).
