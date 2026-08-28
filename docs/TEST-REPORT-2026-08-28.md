# Scenario test report — 2026-08-28 (copy sheet, real LLM, LINE sends captured, DRY_RUN)

Harness: `scripts/scenario_test.py` (calls `main._handle` with fake LineClient). 61 cases. Roster state = copy sheet after today's live swaps.

## Passed (behaviour as designed)
A1/A11/A14/A15/A18/A19 not-on-shift → reject with real value · A2 whole-day (6 lines) · A3 give + "ok ค่ะ" confirm · A4 พี่/น้อง prefixes ·
A4b new report cancels previous; สถานะ/ยกเลิก · A5 ambiguous ธน → asks (ธนดล/ธนวัฒน์) · A6 unknown name → 2 rounds → give-up template ·
A7 missing dates → asks → merged answer → summary · A8 พรุ่งนี้ resolved to 2 ก.ย. · A9 cross-month · A10 same person · A12 duplicate code ·
A13 conference↔เช้า rejected · A17 off day · B1 nurse edit blocked · B2 edit to free slot · B3/B5 edit rejects · C1 head-only · C2 re-publish ·
C3/C6 missing month · C5 · D1/D2/D3/D6 silent · A1b other-user confirm blocked · A1d double confirm · E1b TTL expiry · E2b snapshot mismatch.

## Bugs / gaps found (NOT fixed yet)
1. **Drift detector wrong for grid layout** (`sheets/drift.py`): `_audit.after` holds a *name* in grid layout but `expected_state` treats it as a *code*, so every applied swap becomes a false "drift" (e.g. `('ภควดี', 2, 'นรวิชญ์', '')`). `/cron/drift` would spam the group every 30 min. Real edits are detected (`('ธนดล', 18, 'ช', '')`).
2. **Sheets read quota (60 reads/min/user)**: one report costs ~6 reads (_control, _staff, roster for staff fallback, roster again, colours on apply). Burst of ~8 reports/min → 429; retry backoff (1+2+4 s) sometimes insufficient (A10 took 17 s). Low risk for one ward, real risk with several wards on one service account. Needs caching (_control/_staff per minute) or fewer reads.
3. **`ตารางเวร ส.ค.`** returns a link with no status tag for a month that is neither active nor published (`month_status` = "") — should say (ยังไม่ประกาศ).
4. Two swaps in one message (A16): LLM asks "รายการไหน" instead of taking the first / both — acceptable but undocumented.
5. Roster question (D2 "ใครอยู่เวรดึก 10 ก.ย.") is silent by design — possible feature.
6. "ยืนยัน" with nothing pending goes through the LLM (5 s) before staying silent — could short-circuit.
7. Harness only: `_handle` assumes `groupId` (1:1 events are dropped earlier by the webhook filter — fine in prod).

## Timing
Report → summary 6–9 s (LLM extract ~5 s + sheet reads); confirm ≤1.5 s; commands ≤2 s.
