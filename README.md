# ER แลกเวร (Google Apps Script)

Bound script ของ Sheet `ตารางเวรstaff_ปี2569` — รับคำขอแลกเวรจาก Google Form,
ตรวจว่าเป็นเจ้าของเวรจริง, ส่งอีเมลให้อีกฝ่ายกด approve, แล้วเขียนลงตารางหลักเอง

## Dev

```sh
npm install
npm test                       # unit tests (node --test) ของ lib.gs
```

## Deploy

```sh
npx clasp login
cp .clasp.json.example .clasp.json   # ใส่ scriptId ของ bound script (Extensions ▸ Apps Script ▸ Project settings)
npx clasp push
```

จากนั้นใน Apps Script editor:

1. รัน `setupAll()` ครั้งเดียว (สร้าง Form, Roster/Swap log tab, trigger) — ดู log ได้ URL ของ Form
2. Deploy ▸ New deployment ▸ Web app (Execute as **Me**, Access **Anyone**) → copy URL
3. รัน `setWebAppUrl('https://script.google.com/macros/s/.../exec')`

## กฎ

- แลกได้เฉพาะ `8.00 - 16.00 (1)`, `8.00 - 16.00 (2)` (= แถว On floor 1-2), `16.00 - 24.00`, `0.00 - 8.00` (block 8 ชม. แลกข้ามช่วงได้)
- หลายเวรต่อคำขอ (สูงสุด 4/ฝั่ง) อีกฝ่ายตกลงครั้งเดียว → เขียนทุกช่องพร้อมกัน
- ฝั่งอีกฝ่ายว่าง = ฝากเวร
- state: `pending_b → (pending_head) → committed | rejected | expired | error`

## Files

- `Code.gs` flow หลัก (onFormSubmit / doGet / commitSwap_ / expirePending)
- `lib.gs` pure functions — unit test ได้ใน node
- `app.gs` + `app.html` web app: magic-link login, ตารางรวม (แบบ Excel), เวรฉัน, ประวัติ, ส่งคำขอโดยแตะช่อง
- `setup.gs` setupAll / setupForm / setupTriggers / setWebAppUrl / debugLocate
- `test/` node --test + fixtures (รวม export จากตารางจริง)

Local UI preview: `npm run preview` → http://localhost:3456

รายละเอียด + checklist ทดสอบ: [SETUP.md](SETUP.md) — ผลทดสอบ: [TEST-LOG.md](TEST-LOG.md)
