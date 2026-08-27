# PLAN.md — LINE Shift-Swap Agent (MVP) — v4

> Handoff document for Claude Code. Read fully before writing code.
> Owner: Norawit (CareSync). Context: Thai hospital ward. Nurses agree swaps among themselves offline, then **report** the swap as free text in the LINE group. The agent extracts the swap, checks it against the roster (Google Sheet), asks the reporter to confirm the summary, then writes the change. The Sheet is the single source of truth and **may only be modified through the agent after publish**.

---

## 0. Decisions already made (do not re-open)

| Topic | Decision |
|---|---|
| LLM | OpenAI API. Model via `OPENAI_MODEL` env (current best model with Structured Outputs). Never hardcode a model string. |
| LLM role | Classify + extract + phrase clarifying questions only. **LLM never writes to the Sheet.** All writes are deterministic code after reporter confirmation. |
| Chat platform | LINE Messaging API, LINE OA added to the ward group. Everything happens in LINE. |
| Source of truth | Google Sheet, one spreadsheet per ward, one tab per month. No Excel import. |
| Approval | **None.** Swap agreement happens offline. Only the reporter confirms the agent's summary. No counterparty click, no head-nurse approval. |
| Rules | **None.** No hour limits, no coverage minimum, no skill mix. The only validation is roster consistency (§7). |
| Cross-month swap | Blocked in MVP with a clear message. |
| Direct Sheet edits after publish | Not allowed. Roster tab is protected after publish; every change (swap or single-cell edit) goes through the agent. Draft tab before publish is freely editable by head nurse. |
| App state | SQLite via SQLAlchemy (Postgres-compatible schema). |
| Stack | Python 3.12, FastAPI, `line-bot-sdk` v3, `openai`, `gspread` + `google-auth`. Docker → Cloud Run. Local dev via ngrok. |
| Confirmation UX | LINE Quick Reply postback buttons + free-text fallback ("ยืนยัน" / "ยกเลิก"). |
| Identity | **No persistent LINE-ID ↔ staff mapping for nurses.** Reporter's `userId` is held only inside the open ChangeRequest and deleted on APPLIED/CANCELLED/EXPIRED. Head nurses are identified by `HEAD_NURSE_LINE_IDS` env (1–2 people). Audit records the reporter's LINE display name, not the ID. Every report must name both parties explicitly. |
| Message budget | Reply via reply token wherever possible (free). Push messages (drift alerts, go-live, expiry) count against OA plan quota — keep to a minimum, batch where possible. |

---

## 1. End-to-end user flow (read this first)

Two user groups: **nurses** (report swaps) and **head nurse** (builds roster, publishes, closes, single-cell edits). Everything happens inside one existing LINE group per ward.

### One-time setup
1. Create a LINE OA named after the ward (e.g. "ตารางเวร MED3"), enable "Allow bot to join group chats", invite it into the ward's existing group.
2. Create the ward's Google Sheet. Owner = CareSync-controlled Google account. Share Editor to the service account and to the head nurse.
3. Fill `_staff` (names, nicknames).
4. Put the head nurse's LINE userId(s) in `HEAD_NURSE_LINE_IDS` (get it from the webhook log when they send any message). No onboarding step for other nurses.

### Monthly cycle
1. **~15th–20th** Head nurse copies the template into tab `2569-10` and fills it directly in the Sheet (tab is unprotected while draft).
2. `ตรวจตาราง ต.ค.` → bot checks codes valid, names resolve, no empty rows; replies a report.
3. `ประกาศตาราง ต.ค.` → bot snapshots to `_planned`, protects the tab (service account sole editor), posts link in group.
4. **Day 1** tab flips to `live` automatically (cron).
5. **Month end** `ปิดตาราง ก.ย.` → bot builds `_diff` (planned vs actual), replies swap count + per-person delta, tab stays protected forever.

### Daily: swap report
1. Nurses agree offline. One of them types in the group, e.g. "แลกเวรดึก 3 ต.ค. ของศรี กับ เช้า 5 ต.ค. ของบี".
2. Bot extracts. Missing fields / ambiguous name → asks back (max 2 rounds).
3. Bot checks the roster: ศรี really on ด day 3? บี really on ช day 5? no duplicate code after swap? same month?
   - Mismatch → reply with the real roster value ("ศรี วันที่ 3 ตารางระบุ บ ไม่ใช่ ด"). No buttons. Done.
   - Match → reply summary + [ยืนยัน] [ยกเลิก].
4. **Only the reporter** may tap ยืนยัน → bot writes both cells in one batch + audit row + posts "อัปเดตตารางแล้ว".
5. No tap within 2 h → expired.

### Daily: single-cell edit (head nurse only)
"เปลี่ยนศรี วันที่ 5 เป็นดึก" or "บี วันที่ 12 หยุด" → summary → ยืนยัน → write. Same path as swap.

### Silent behaviour
- Non-roster messages: classified, discarded, never stored, never replied to.
- Every 30 min: drift check on live/published tabs. Out-of-band edit found → post to group, do not auto-revert.

### Explicitly absent
No approval step. No counterparty confirmation. No hour/coverage rules. No cross-month swap. No roster generation.

---

## 2. Scope

### In scope (MVP)
1. Bot receives all group messages; classifies swap reports / edit requests / commands; ignores everything else silently.
2. Extracts structured swap from Thai free text; asks clarifying question when fields missing or names ambiguous.
3. Consistency check against roster: both people actually hold the claimed shifts on the claimed days.
4. Reporter confirms summary → Sheet updated in one batch → audit row → group notified.
5. Single-cell roster edit by head nurse via free text (`roster_edit` intent), same confirm → write path.
6. Monthly commands: `ตรวจตาราง`, `ประกาศตาราง`, `ปิดตาราง`, `สถานะ`, `ยกเลิก`.
7. Sheet protection applied on publish and kept permanently (§8).

### Out of scope
- Roster generation, rule validation, coverage, hour limits.
- Counterparty / head-nurse approval workflow.
- Cross-month swaps.
- Multi-ward in one group.
- OT / payroll calc (only planned-vs-actual diff export).

---

## 3. Architecture

```
LINE group ──webhook──▶ FastAPI (/webhook)
                            │
                            ├─ verify signature; drop if groupId not whitelisted; text only
                            ├─ command router (exact-match Thai, before LLM)
                            ├─ classify (OpenAI, structured) ──▶ swap_report | roster_edit | confirm_reply | other
                            ├─ extract (OpenAI, structured)
                            ├─ name_resolver (deterministic, _staff tab)
                            ├─ consistency check vs roster (deterministic)
                            ├─ create ChangeRequest → reply summary + [ยืนยัน] [ยกเลิก]
                            └─ postback / "ยืนยัน" by same user → SheetWriter.apply → _audit → notify

Google Sheets (per ward) ◀── gspread (service account, sole editor after publish)
```

LINE webhook must return 200 fast → run LLM + sheet work in `BackgroundTask`; use `reply_message` if within reply-token window, else `push_message` to groupId.

---

## 4. Google Sheet schema

One spreadsheet per ward. **Spreadsheet owner = CareSync/service Google account**, head nurse has Editor on the file. This matters for protection (§8): an owner can bypass protected ranges, an editor cannot.

### Tab `_control`
| key | value |
|---|---|
| ward_code | `MED3` |
| active_months | `2569-09,2569-10` |
| status:2569-10 | `draft` / `published` / `live` / `closed` |
| published_at:2569-10 | ISO ts |
| published_by:2569-10 | staff_id |

Lifecycle `draft → published → live → closed`. `live` set automatically on day 1 of month (cron). Changes allowed only on tabs with status ∈ {`published`, `live`}.

### Tab `_staff`
| staff_id | full_name_th | nicknames | active |
|---|---|---|---|
| N001 | สมศรี ใจดี | ศรี,พี่ศรี | TRUE |

Name resolution: normalize, strip พี่/น้อง/คุณ/หมอ, match full name + nicknames. 0 or >1 match → clarifying question. **Never guess a person.**
No LINE identifiers in this tab. Authorship of a report is captured at request time from the group member profile (display name) — see `_audit`.

### Tab `<YYYY-MM>` (BE year, e.g. `2569-10`)
| staff_id | name | 1 | 2 | … | 31 |
|---|---|---|---|---|---|
| N001 | สมศรี | ช | ด | … | |

Shift codes (`config/shifts.yaml`):

| code | text synonyms (for extraction) |
|---|---|
| `ช` | เช้า, ช, morning |
| `บ` | บ่าย, บ |
| `ด` | ดึก, ด, night |
| `conference` | conference, ประชุม, conf |
| *(empty)* | off, หยุด, ว่าง |

A cell may hold multiple codes (e.g. `ชบ`) — parser splits into a set. Swap operates on **one code** within the cell; the other codes stay. `conference` is treated as a normal swappable code (assumption — flag to owner if wrong).

### Tab `<YYYY-MM>_planned` — frozen copy at publish. Never edited.
### Tab `<YYYY-MM>_diff` — created at close: rows where planned ≠ actual.
### Tab `_audit` (append-only)
| ts | month | staff_id | day | before | after | change_id | reporter_display_name | kind (`swap`/`edit`) | raw_text |

`reporter_display_name` comes from `get_group_member_profile(groupId, userId)` at request time. The userId itself is never written to the Sheet.

---

## 5. Data model (SQLite)

```python
class ChangeRequest:
    id: str                      # short id shown in chat, e.g. "A1B2"
    kind: Literal["swap", "edit"]
    group_id: str
    month: str                   # "2569-10"
    reporter_line_id: str        # transient: nulled on APPLIED/CANCELLED/EXPIRED/REJECTED
    reporter_display_name: str   # from group member profile at request time
    # swap fields
    a_staff_id: str | None
    a_day: int | None
    a_shift: str | None          # code A gives to B
    b_staff_id: str | None
    b_day: int | None
    b_shift: str | None          # code B gives to A
    swap_type: Literal["exchange", "give"] | None   # give = one-way, b_day/b_shift null
    # edit fields
    target_staff_id, target_day: ...
    old_value: str | None        # full cell string captured at request time
    new_value: str | None
    state: Literal["PENDING_CLARIFICATION", "PENDING_CONFIRM",
                   "APPLIED", "REJECTED", "CANCELLED", "EXPIRED"]
    raw_text: str
    llm_extraction: JSON
    check_result: JSON
    snapshot: JSON               # cell values at request time (for optimistic lock)
    created_at, updated_at, expires_at   # TTL default 2h (confirm should be immediate)

```

State machine (`change/state_machine.py`, single place):

```
msg ─▶ PENDING_CLARIFICATION (missing fields / ambiguous name) ─answer─▶ re-extract (max 2 rounds → CANCELLED)
    └▶ consistency check fails ─▶ REJECTED (reply reason, no button)
    └▶ PENDING_CONFIRM ─reporter taps ยืนยัน─▶ APPLIED (write ok)
                       ─reporter taps ยกเลิก / พิมพ์ ยกเลิก─▶ CANCELLED
                       ─anyone else taps─▶ ignore + short reply "เฉพาะผู้แจ้งเท่านั้น"
                       ─TTL─▶ EXPIRED
```

Only the **reporter's** `source.userId` may confirm — compare against `reporter_line_id` on the open request, server-side; never trust postback payload alone. On any terminal state set `reporter_line_id = NULL` (data minimization). One open PENDING_CONFIRM per reporter — a new report auto-cancels the previous one.

---

## 6. LLM layer (OpenAI, Structured Outputs `strict: true`)

### 5.1 Classify
```json
{ "intent": "swap_report | roster_edit | confirm_reply | command | other", "confidence": 0.0 }
```
Proceed only if confidence ≥ 0.6. `other` → silent, nothing stored. `roster_edit` only honoured if `source.userId` ∈ `HEAD_NURSE_LINE_IDS`; otherwise reply "การแก้เวรเดี่ยวทำได้เฉพาะหัวหน้าเวร".

### 5.2 Extract (swap)
```json
{
  "swap_type": "exchange | give | null",
  "a_name": "str|null", "a_day": "int|null", "a_month": "str|null", "a_shift": "ช|บ|ด|conference|null",
  "b_name": "str|null", "b_day": "int|null", "b_month": "str|null", "b_shift": "ช|บ|ด|conference|null",
  "missing": ["..."],
  "clarifying_question_th": "str|null"
}
```
- Both `a_name` and `b_name` are **required** (for `give`, `b_name` required, `b_day/b_shift` null). There is no sender→name default; if a party is unnamed → `missing` + clarifying question. Few-shots must include "ขอแลกเวร..." without a name → question "แลกของใครกับใครคะ".
- Today given in CE + BE. Resolve relative dates; if day already passed and month unspecified → assume next active month and add `month_ambiguous` to `missing`.
- If `a_month != b_month` → reject with "ยังไม่รองรับการแลกข้ามเดือน".
- Few-shot in `prompts/extract_examples.jsonl`, ≥ 30 Thai messages covering: full report, give-only, missing shift, missing day, nickname-only, "ok ค่ะ" (confirm_reply), chit-chat.

### 5.3 Extract (edit)
```json
{ "target_name": "str|null", "day": "int|null", "month": "str|null", "new_shift": "str|null", "missing": [], "clarifying_question_th": "str|null" }
```
e.g. "เปลี่ยนพี่ศรี วันที่ 5 เป็นดึก", "พี่บี วันที่ 12 หยุด" (→ empty).

Extraction is advisory; code re-validates day range, code validity, name resolution. Any failure → clarifying question, never a guess.

### 5.4 Clarification loop
Reply quoting request + `clarifying_question_th`. Next message from same user within 10 min is merged and re-extracted. Max 2 rounds, then reply with a template example and CANCEL:
> "รบกวนพิมพ์ใหม่ เช่น: แลกเวรดึก 3 ต.ค. ของศรี กับ เช้า 5 ต.ค. ของบี"

---

## 7. Consistency check (deterministic, `change/checks.py`)

This is the agent's whole job. On the current roster tab:

| check | on fail |
|---|---|
| Month status ∈ {published, live} | reject: "ตารางเดือนนี้ยังไม่ประกาศ / ปิดแล้ว" |
| Day exists in month | reject |
| A's cell on a_day contains `a_shift` | reject: "ศรี ไม่ได้อยู่เวรดึกวันที่ 3 (ตารางระบุ: บ)" |
| B's cell on b_day contains `b_shift` (exchange only) | reject, same format |
| A ≠ B | reject |
| After swap, A's new cell does not already contain the incoming code (no `ดด`) | reject: "ศรี มีเวรดึกวันที่ 5 อยู่แล้ว" |
| Edit: target cell currently equals what reporter implied (if they stated old value) | warn in summary only |

Reject replies show the actual roster value so the reporter can fix the report. No buttons on reject.

---

## 8. Sheet writer + protection (`sheets/`)

- Read tab once per operation (`get_all_values`). Never cell-by-cell reads.
- Write both cells + audit rows in one `batch_update`.
- **Optimistic lock**: re-read the affected cells right before writing; must equal `snapshot`. If not → REJECTED: "ตารางถูกแก้ระหว่างรอ กรุณาแจ้งใหม่".
- Retry with backoff on 429/5xx.
- **Protection**: on `ประกาศตาราง`, add a protected range covering the whole roster tab with editors = [service account only]. `_planned` tab likewise. On `ปิดตาราง`, keep protection (closed months are immutable). Draft tabs are unprotected.
- **Drift detector** (cron every 30 min on live/published tabs): compare tab to last-known state reconstructed from `_planned` + `_audit`. Any mismatch → push to group "พบการแก้ตารางนอกระบบ ที่ N001 วันที่ 7 (ด → ช)" and log. Do not auto-revert.

---

## 9. Commands (exact-match router before LLM)

"head nurse" below = `source.userId` ∈ `HEAD_NURSE_LINE_IDS`.

| Command | Who | Action |
|---|---|---|
| `ประกาศตาราง 2569-10` | head nurse | Parse sanity (codes valid, staff_ids exist) → copy to `_planned` → status=published → protect → announce with link |
| `ตรวจตาราง 2569-10` | head nurse | Report parse errors: unknown codes, unknown staff, empty rows. (No rules.) |
| `ปิดตาราง 2569-09` | head nurse | status=closed → build `_diff` tab → reply summary (n changes, per-person delta) |
| `สถานะ` | anyone | Own pending change, if any |
| `ยกเลิก` | reporter | Cancel own pending change |

Month parser accepts `2569-10`, `10/2569`, `ต.ค.`, `ตุลาคม`, `ต.ค. 69`.

---

## 10. Message templates (`templates/th.py`) — short, phone-readable

**Summary (PENDING_CONFIRM):**
```
🔄 สรุปการแลกเวร #A1B2
3 ต.ค. ดึก: ศรี → บี
5 ต.ค. เช้า: บี → ศรี
ถูกต้องไหม?
[ยืนยัน] [ยกเลิก]
```
**Give:**
```
🔄 สรุป #A1B2
12 ต.ค. บ่าย: ศรี → บี (ยกเวร)
[ยืนยัน] [ยกเลิก]
```
**Applied:**
```
📋 อัปเดตตารางแล้ว #A1B2
3 ต.ค. ดึก: ศรี → บี
5 ต.ค. เช้า: บี → ศรี
```
**Reject:**
```
❌ แจ้งไม่ตรงตาราง
ศรี วันที่ 3 ต.ค. ตารางระบุ "บ" ไม่ใช่ "ด"
ตรวจสอบแล้วแจ้งใหม่ได้เลย
```
Postback data: `action=confirm&id=A1B2` / `action=cancel&id=A1B2`.

---

## 11. Security / PDPA

- Whitelist `groupId`s; ignore all 1:1 messages entirely.
- Store text only for `swap_report` / `roster_edit`. `other` is discarded after classification, never logged.
- No persistent LINE userId storage anywhere (DB, Sheet, logs) except `HEAD_NURSE_LINE_IDS` in env and the transient `reporter_line_id` on open requests.
- Do not send any LINE identifier or display name to OpenAI. Send the staff name list only if extraction needs it (prefer resolving in code).
- Secrets via env; `.env.example` committed.
- JSON logs to stdout; message text at DEBUG only.

---

## 12. Repo layout

```
line-swap-agent/
├── PLAN.md
├── README.md              # LINE OA setup, service-account sharing, ownership note (§4), ngrok, deploy
├── pyproject.toml
├── Dockerfile
├── .env.example
├── config/shifts.yaml
├── prompts/{classify.md, extract_swap.md, extract_edit.md, extract_examples.jsonl}
├── src/agent/
│   ├── main.py            # FastAPI: /webhook, /healthz, /cron/expire, /cron/drift, /cron/go-live
│   ├── settings.py
│   ├── line/              # client, signature, templates, postback parsing
│   ├── llm/               # client, pydantic schemas, classify(), extract_swap(), extract_edit()
│   ├── sheets/            # reader, writer, control, staff, audit, protection, drift
│   ├── change/            # models, state_machine, service, checks, name_resolver
│   ├── commands/
│   ├── thai_date.py
│   └── db.py
├── tests/
│   ├── fixtures/roster_2569-10.csv
│   ├── test_thai_date.py
│   ├── test_extract_thai.py      # recorded OpenAI responses; no live calls in CI
│   ├── test_name_resolver.py
│   ├── test_checks.py
│   ├── test_state_machine.py
│   └── test_sheet_writer.py      # gspread mocked
└── scripts/seed_sheet.py
```

---

## 13. Env vars

```
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=
LINE_ALLOWED_GROUP_IDS=Cxxxx
OPENAI_API_KEY=
OPENAI_MODEL=
GOOGLE_SERVICE_ACCOUNT_JSON=
SHEET_ID_MAP=Cxxxx:1AbC...
HEAD_NURSE_LINE_IDS=Uaaaa,Ubbbb   # only persistent LINE IDs in the system
DATABASE_URL=sqlite:///./agent.db
CHANGE_TTL_HOURS=2
DRY_RUN=false          # true = log intended writes, don't touch Sheet
LOG_LEVEL=INFO
```

---

## 14. Milestones

**M1 — Skeleton (d1–2)**: webhook + signature; `thai_date` with tests; sheet reader → typed objects; seed script.
✅ pytest green; bot in test group receives events.

**M2 — Extraction (d3–5)**: classify/extract with Structured Outputs; 30+ fixtures; name resolver.
✅ ≥ 90% field accuracy on fixtures; **0 wrong-name resolutions** (ambiguous → question).

**M3 — Change workflow (d6–8)**: ChangeRequest, state machine, consistency checks, Quick Reply, reporter-only confirm, writer with optimistic lock + audit.
✅ E2E in test group: report → summary → ยืนยัน → cells updated → audit row. Reject path shows real roster value.

**M4 — Monthly commands + protection (d9–11)**: publish/close/ตรวจ/สถานะ/ยกเลิก; protection on publish; drift cron; go-live cron.
✅ Publish seeded month → 3 swaps + 1 edit → head nurse tries direct edit and is blocked → close → `_diff` correct.

**M5 — Deploy (d12–13)**: Dockerfile, Cloud Run, README, PDPA checklist.
✅ Live webhook; 1-week shadow run in real ward group with `DRY_RUN=true`.

---

## 15. Assumptions to confirm with owner (non-blocking)
1. `conference` is swappable like any other code.
2. Empty cell = off (no explicit OFF code in the sheet).
3. Spreadsheet ownership can be moved to a CareSync-controlled Google account (required for protection to be enforceable against head nurse).

## 16. Non-goals for Claude Code (do not add unprompted)
- No web dashboard. No queue/Redis/Postgres. No rule engine. No approval flow. No LLM tool that writes to Sheets. No non-Thai templates.
