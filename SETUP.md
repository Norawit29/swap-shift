# SETUP — ER แลกเวร

## 1. เตรียม Sheet (copy สำหรับทดสอบ)

1. ทำสำเนา `ตารางเวรstaff_ปี2569` → ใช้ Sheet ID ของ **copy** ตลอดการทดสอบ
2. Extensions ▸ Apps Script → Project settings → copy **Script ID**

## 2. Push โค้ด

```sh
./deploy.sh        # ทำให้ทั้งหมด: login → clasp create --parentId <copy> → push → deploy
```

## 3. รัน setupAll (ครั้งเดียว)

Apps Script editor ▸ เลือก `setupAll` ▸ Run ▸ อนุมัติ scope (Sheets, Forms, Mail, Triggers)

สิ่งที่เกิดขึ้น:
- tab `Roster` (คอลัมน์ `ชื่อในตาราง | อีเมล | บทบาท`) — ถ้าว่าง จะใส่ mock 2 บัญชี:
  `norawit29 / norawit29@gmail.com` และ `norawit.kij / norawit.kij29@gmail.com (head)`
- tab `Swap log`
- Google Form `ER แลกเวร` (Verified email, dropdown ชื่อจาก Roster, เวรฝั่งละ 4 slot) เชื่อม destination เข้า Sheet นี้
- trigger `onFormSubmit` + `expirePending` (ทุกวัน 08:00)
- Script Property `FORM_ID`

ดู Execution log → URL ของ Form

## 4. Deploy web app

Deploy ▸ New deployment ▸ Web app — Execute as **Me**, Who has access **Anyone** → copy URL `/exec`
แล้วรัน `setWebAppUrl('https://script.google.com/macros/s/.../exec')`

(optional) `setAdminEmail('ธุรการ@...')`, `setRequireHeadApproval(true)`, `setPendingDays(3)` — ดูค่าปัจจุบันด้วย `showConfig()`

## 5. ใส่ชื่อ mock ลงตาราง (เฉพาะ copy ทดสอบ)

`setupAll` จะใส่ให้อัตโนมัติ (`seedMockNames`) เมื่อชื่อไฟล์ขึ้นต้น "Copy of" — หรือใส่เองตามนี้: ชื่อใน Roster ต้องตรงกับชื่อในช่องเวร ให้แก้ tab เดือนที่ทดสอบ (เช่น `กันยายน2569 (แลก5)` — script ใช้ tab **ขวาสุด** ของเดือนนั้น) ใส่ชื่อ:

| ช่อง | ใส่ชื่อ |
|---|---|
| 10 ก.ย. `8.00 - 16.00` | norawit29 |
| 11 ก.ย. `16.00 - 24.00` | norawit29 |
| 12 ก.ย. `0.00 - 8.00` | norawit.kij |
| 14 ก.ย. `8.00 - 16.00 (2)` (แถว On floor 1-2) | norawit.kij |

ตรวจว่า script หาเจอ: รัน `debugLocate('2026-09-10', '8.00 - 16.00')` → log ต้องได้ `value: "norawit29"`

## 5b. Web app (login)

เปิด `WEB_APP_URL` ตรงๆ (ไม่มี param) = หน้าเว็บ: กรอกอีเมล → ได้ **ลิงก์เข้าสู่ระบบ** ทางอีเมล (15 นาที ใช้ครั้งเดียว) → session 30 วันใน browser
- ต้องเป็นอีเมลใน Roster เท่านั้น (Gmail หรือ @chula ก็ได้ — ไม่ใช้ Google login/domain)
- หน้า: ตารางเวรรวม (เหมือน Excel, เดือนละ tab ขวาสุด) / เวรของฉัน / ประวัติที่เกี่ยวกับฉัน / ส่งคำขอโดยแตะช่องในตาราง (ช่องฉัน = ให้, ช่องคนอื่น = รับ) → ส่งครั้งเดียว ใช้ flow อีเมล approve เดิม
- session/login token เก็บใน tab ซ่อน `Sessions` (ล้างอัตโนมัติโดย expirePending)
- ทดสอบ: เพิ่ม case **W1** login ด้วย norawit29@gmail.com → เห็นตาราง ก.ย. ช่องของตัวเองไฮไลต์ **W2** แตะช่องตัวเอง 2 ช่อง + ช่อง norawit.kij 1 ช่อง → ส่ง → norawit.kij29 ได้อีเมล approve เหมือน Form **W3** ประวัติแสดงคำขอทั้งที่ตัวเองเป็น A และ B

## 6. กฎที่ script บังคับ

- อีเมลที่ส่ง Form (verified) ต้องตรงกับอีเมลของ "ชื่อคุณ" ใน Roster
- เวรที่แลกได้: `8.00 - 16.00 (1)` (แถว 8.00 - 16.00), `8.00 - 16.00 (2)` (แถว On floor 1-2), `16.00 - 24.00`, `0.00 - 8.00` (block ละ 8 ชม. แลกข้ามช่วงได้) — ไม่รวม conference
- ทุกเวรที่กรอก ต้องเป็นของเจ้าตัว **ณ ตอนส่ง Form** และ **ณ ตอน commit** (re-validate)
- หลายเวรในคำขอเดียว → อีกฝ่ายตกลง/ปฏิเสธครั้งเดียวทั้งชุด → เขียนทุกช่อง หรือไม่เขียนเลย
- ช่องที่มีคำขอ pending อยู่ ยื่นซ้ำไม่ได้จนกว่าจะ committed/rejected/expired
- ลิงก์ approve/reject ใช้ได้ครั้งเดียว (token ถูกล้างหลังใช้) — กดซ้ำจะได้หน้า "ดำเนินการแล้ว"
- ฝั่ง B ว่าง = ฝากเวร

## 7. Checklist ทดสอบ (บน copy) — บันทึกผลใน TEST-LOG.md

จับเวลาแต่ละ action (Form submit → อีเมลถึง, กด approve → หน้า "สำเร็จ") ต้อง < 10 วินาที

| # | ขั้นตอน | ผลที่คาด |
|---|---|---|
| 1 | **Happy path หลายเวร**: login `norawit29@gmail.com` ส่ง Form: ชื่อคุณ=norawit29, เวร #1 = 10 ก.ย. `8.00 - 16.00`, #2 = 11 ก.ย. `16.00 - 24.00`; อีกฝ่าย=norawit.kij, เวร #1 = 12 ก.ย. `0.00 - 8.00`, #2 = 14 ก.ย. `8.00 - 16.00 (2)` | `Swap log` มีแถว `pending_b`; norawit.kij29 ได้อีเมลมีปุ่ม 2 ปุ่ม + รายการ 4 เวร; norawit29 ได้อีเมล "ส่งคำขอแล้ว" |
| 1b | กด **ตกลงทั้งหมด** ในอีเมล | หน้า "แลกเวรสำเร็จ (4 ช่อง)"; ตาราง: 10/11 ก.ย. เป็น norawit.kij, 12/14 ก.ย. เป็น norawit29; log = `committed`; ทั้งสองได้อีเมล |
| 1c | กดลิงก์เดิมซ้ำ (หรือ back แล้ว refresh) | หน้า "คำขอนี้ถูกดำเนินการแล้ว" ตารางไม่เปลี่ยน |
| 2 | **Reject**: ส่ง Form แลกกลับ (norawit29 ขอ 12 ก.ย. `0.00 - 8.00` ↔ norawit.kij 10 ก.ย. `8.00 - 16.00`) แล้วกด **ปฏิเสธ** | log = `rejected`; norawit29 ได้อีเมลปฏิเสธ; ตารางไม่เปลี่ยน |
| 3 | **ไม่ใช่เจ้าของ**: norawit29 ส่ง Form อ้างเวร 10 ก.ย. `8.00 - 16.00` (ตอนนี้เป็นของ norawit.kij แล้ว) | log = `error` message บอกว่าช่องเป็นของ "norawit.kij"; norawit29 ได้อีเมล error; ไม่มีอีเมลถึง norawit.kij |
| 3b | **อีเมลไม่ตรง**: login `norawit.kij29@gmail.com` แต่เลือกชื่อคุณ = norawit29 | log = `error` "อีเมลที่ส่ง Form ไม่ตรง…" |
| 3c | **ฝากเวร**: norawit.kij ส่ง Form เวรของคุณ = 10 ก.ย. `8.00 - 16.00`, อีกฝ่าย = norawit29, ไม่กรอกเวรอีกฝ่าย → norawit29 ตกลง | type=`give`; 10 ก.ย. กลับเป็น norawit29; log = `committed` |
| 4 | **ซ้อน pending**: ส่งคำขอ X บนเวร 11 ก.ย. `16.00 - 24.00` (ยังไม่กดตอบ) แล้วส่งคำขอ Y บนเวรเดียวกัน | Y = `error` "มีคำขอ SW… ที่ยังรอตอบรับ"; X ยัง `pending_b` |
| 4b | **ตารางถูกแก้ระหว่างรอ**: แก้ช่อง 11 ก.ย. ในตารางด้วยมือเป็นชื่ออื่น แล้วกดตกลง X | หน้า "เขียนตารางไม่สำเร็จ"; log = `error`; ตารางไม่ถูกเขียนแม้แต่ช่องเดียว; ทุกฝ่ายได้อีเมล error |
| 5 | **Expire**: ส่งคำขอใหม่ (pending_b) แล้วรัน `expirePending(0)` ใน editor | log = `expired`; ทั้งสองได้อีเมลหมดอายุ; กดลิงก์ในอีเมลเดิม → "ดำเนินการแล้ว" |
| W1–W3 | web app (ดู 5b) | ตาราง/ส่งคำขอ/ประวัติ ทำงาน; อีเมลถึง B เหมือน Form |
| 5b | (ถ้าเปิด head) `setRequireHeadApproval(true)` → ส่งคำขอ → B ตกลง | log = `pending_head`, head (norawit.kij29) ได้อีเมล → ตกลง → `committed`; ปิดกลับด้วย `setRequireHeadApproval(false)` |

ผ่านครบ → cutover ตามแผนข้อ 6 (push ไป script ของ Sheet จริง, setupAll, deploy, setWebAppUrl, แก้ Roster เป็นรายชื่อจริง, protect tab)

## หมายเหตุ

- script แก้ตารางใน tab ปัจจุบัน **in place** (ไม่ copy tab `(แลกN)` ใหม่เหมือนที่ธุรการทำมือ) — ประวัติอยู่ใน `Swap log`
- บังคับ tab ของเดือนได้ด้วย Script Property `TAB_2026-09 = กันยายน2569 (แลก5)`
- Roster เปลี่ยน → รัน `refreshFormRoster()` เพื่ออัปเดต dropdown
- MailApp quota Gmail ส่วนตัว 100 ฉบับ/วัน (Workspace 1,500) — 1 swap ≈ 4 ฉบับ
