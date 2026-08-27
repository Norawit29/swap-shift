# PLAN — ER Shift Swap Workflow (Google Apps Script)

## Context

ตารางเวร attending ER อยู่ใน Google Sheet `ตารางเวรstaff_ปี2569` (เดือนละ 1 tab) ปัญหา: แลกเวรผ่าน LINE → ธุรการแก้ตาราง → บางครั้งไม่ได้แก้ → คนลืมแล้วแลกซ้ำ

เป้าหมาย: แลกเวรต้องผ่าน Google Form → script validate ว่าเป็นเจ้าของเวรจริง ณ ตอนนี้ → email ให้อีกฝ่ายกด approve → script เขียนลงตารางหลักเอง

**มีโค้ดร่างแล้วใน `Code.gs`** (ทำงานได้ end-to-end แต่ยังไม่ได้ทดสอบกับ Sheet จริง) — งานของคุณคือทำให้ deploy ได้จริง ทดสอบได้ และลดขั้นตอน manual

## Layout ตารางหลัก (ดูจาก screenshot จริง)

- คอลัมน์ B = label แถว, C–I = จันทร์–อาทิตย์
- แต่ละสัปดาห์เป็น block: แถว `วันที่` (ค่าเช่น `10`, `8R con*`, `9*Interhos*`, `18ems` — ขึ้นต้นด้วยเลขวัน) ตามด้วยแถวเวร `8.00 - 16.00`, `On floor 1-2`, `conference 3-4`, `conference 3-4,TM`, `16.00 - 24.00`, `0.00 - 8.00`
- Block แรกเริ่มแถว 3 (แถว 1 = title "ตารางเวร Staff กันยายน 2569", แถว 2 = ชื่อวัน)
- ช่องเวรมีชื่อหมอ บางช่องมี suffix ` TM` และมี merged cell ในแถว conference
- ช่องว่าง = ไม่มีเวร

## Tech constraints

- Google Apps Script bound to the Spreadsheet (ไม่ใช่ standalone) — ต้อง `clasp` เพื่อ push จาก local
- ผู้ใช้เป็น Gmail ส่วนตัวผสม @chula.ac.th → **ห้าม**พึ่ง domain restriction / `Session.getActiveUser()` ใน web app; ใช้ Form "Verified email" + Roster tab + token link เท่านั้น
- Web app deploy: Execute as Me, Access Anyone
- Owner ทั้งหมด = บัญชีกลางของภาค
- ห้ามใช้ library ภายนอก; V8 runtime

## Tasks

### 1. Project scaffold
- [ ] `npm init`, ติดตั้ง `@google/clasp` (dev), `.clasp.json` ชี้ scriptId (ผมจะให้ตอน login) , `appsscript.json` ตั้ง `timeZone: Asia/Bangkok`, `runtimeVersion: V8`, `webapp: {executeAs: USER_DEPLOYING, access: ANYONE_ANONYMOUS}`, oauthScopes: spreadsheets, forms, script.send_mail, script.scriptapp
- [ ] `.gitignore`: `.clasp.json`, `node_modules`
- [ ] `README.md` สั้นๆ: clasp login → clasp push → clasp deploy

### 2. แยกโค้ดให้ทดสอบได้
- [ ] แยก pure functions ออกจาก `Code.gs` เป็น `lib.gs`: `parseFormDate_`, `fmtDate_`, `baseName_`, `cellHasName_`, `replaceName_`, `normLabel_`, `colIndex_`, และ `findShiftInGrid_(labels[], grid[][], day, shiftLabel) → {r, c} | {error}` (ดึง logic จาก `locateShift_` ให้ไม่แตะ SpreadsheetApp)
- [ ] `test/lib.test.js` ด้วย node built-in test runner (`node --test`) — Apps Script ไฟล์ .gs โหลดใน node ได้โดย `vm` หรือ concat; เลือกวิธีที่ง่ายสุด
- [ ] Fixture `test/fixtures/september-2569.json`: labels + grid จำลองจาก layout ข้างบน อย่างน้อย 2 สัปดาห์ รวม case `8R con*`, `9*Interhos*`, `18ems`, ช่องว่าง, ` TM` suffix
- [ ] Test cases ขั้นต่ำ:
  - day 10 / `8.00 - 16.00` → เจอ cell ถูกต้อง
  - day 8 (`8R con*`) → parse เลขวันได้
  - `On floor 1-2` เทียบ label แบบ ignore whitespace/case
  - `cellHasName_('สุรีย์ภรณ์ TM', 'สุรีย์ภรณ์')` = true
  - `replaceName_('สุรีย์ภรณ์ TM','สุรีย์ภรณ์','ธนดล')` = `ธนดล TM`
  - `parseFormDate_` รับ `2026-09-10`, `10/09/2026`
  - วันไม่มีในตาราง → error

### 3. ลดขั้นตอน manual: สร้าง Form ด้วย script
- [ ] เพิ่ม `setupForm()` ใน `setup.gs`: `FormApp.create('ER แลกเวร')` → ตั้ง collect email Verified (`setRequireLogin(true)` + `setCollectEmail(true)`) → สร้างคำถามตาม object `Q` และ dropdown ชื่อจาก Roster → `setDestination(SPREADSHEET, ss.getId())` → เขียน form ID กลับไปที่ `PropertiesService.getScriptProperties()` key `FORM_ID`
- [ ] เปลี่ยน `CONFIG.FORM_ID` และ `CONFIG.WEB_APP_URL` ให้อ่านจาก Script Properties (fallback ค่าใน CONFIG) เพื่อไม่ต้องแก้โค้ดตอน deploy
- [ ] `setupAll()` = setupForm → setupTriggers → log URL ของ Form และเตือนให้ deploy web app แล้ว set property `WEB_APP_URL`

### 4. Review Code.gs
- [ ] ตรวจ `onFormSubmit` กรณี `e.namedValues` key ของอีเมลใน Form ภาษาไทย = `ที่อยู่อีเมล` (มี fallback แล้ว ยืนยันว่าถูก)
- [ ] `nextSwapId_` + `appendLog_` ภายใต้ `LockService` แล้ว — ยืนยันว่า `doGet` ที่ commit ก็ถือ lock เดียวกัน (ป้องกัน B กดสองครั้งเร็วๆ)
- [ ] `expirePending` ใช้ `updated_at` เป็นฐาน — ถ้าเข้า `pending_head` นาฬิกาจะ reset ซึ่งตั้งใจ ยืนยัน
- [ ] `commitSwap_` re-validate ก่อนเขียน แล้ว `SpreadsheetApp.flush()` — ok
- [ ] ถ้าเจอ bug แก้ได้เลย แต่ห้ามเปลี่ยน state machine: `pending_b → (pending_head) → committed | rejected | expired | error`

### 5. Dev/test on a copy
- [ ] ผมจะให้ Sheet ID ของ **copy** ของตารางจริง — ทุกอย่างทดสอบบน copy นี้ก่อน
- [ ] Roster ใน copy ใส่อีเมลทดสอบ 2 บัญชีของผม
- [ ] รัน checklist ใน `SETUP.md` ข้อ 7 ให้ครบ บันทึกผลใน `TEST-LOG.md`

### 6. Cutover (ผมทำเอง หลังคุณส่งมอบ)
- clasp push ไป script ของ Sheet จริง → setupAll → deploy → set WEB_APP_URL → protect tabs → ประกาศกฎ

## Acceptance criteria

1. `npm test` ผ่านทั้งหมด
2. `clasp push` แล้ว `setupAll` รันจบไม่มี error สร้าง Form + trigger + Swap log ให้เอง
3. Flow ทดสอบ 5 ข้อใน SETUP.md ผ่านบน copy sheet
4. Form submit → commit ใช้เวลารวม < 10 วินาที ต่อ action
5. ไม่มีขั้นตอนที่ต้องแก้โค้ดตอน deploy (config อยู่ใน Script Properties)

## Non-goals (รอบนี้)

- Sync ไป Google Calendar / LINE notify
- UI dashboard
- Multi-month swap ข้ามไฟล์
- Undo/rollback swap ที่ commit แล้ว (ทำ manual ผ่านธุรการ + note ในช่อง)

## Files

```
er-swap/
  Code.gs        ← มีอยู่แล้ว (flow หลัก)
  lib.gs         ← สร้าง (pure functions)
  setup.gs       ← สร้าง (setupForm, setupAll, setupTriggers ย้ายมา)
  appsscript.json
  SETUP.md       ← มีอยู่แล้ว อัปเดตให้ตรงหลังทำ task 3
  test/
  package.json
```

เริ่มจาก task 1–2 แล้วรายงานก่อนทำ 3 (task 3 ต้องการ scriptId + Sheet ID จากผม)
