/**
 * setup.gs — รันครั้งเดียวจาก Apps Script editor (หลัง clasp push)
 *
 *   setupAll()                 สร้าง Roster/Swap log tab, Form, trigger  → log URL ของ Form
 *   setWebAppUrl(url)          หลัง Deploy web app → เก็บ URL ลง Script Properties
 *   setAdminEmail(email)       (optional) อีเมลธุรการ cc ทุก commit/error
 *   setRequireHeadApproval(b)  (optional) เปิดขั้น head approve
 *   refreshFormRoster()        Roster เปลี่ยน → อัปเดต dropdown ชื่อใน Form
 *
 * config ทั้งหมดอยู่ใน Script Properties — ไม่ต้องแก้โค้ดตอน deploy
 */

// บัญชีทดสอบ (mock) — ใส่ให้เฉพาะตอน Roster ยังว่างเปล่า
var MOCK_ROSTER_ = [
  ['norawit29', 'norawit29@gmail.com', ''],
  ['norawit.kij', 'norawit.kij29@gmail.com', 'head']
];

function setupAll() {
  setupSheets_();
  if (/^copy of/i.test(SpreadsheetApp.getActiveSpreadsheet().getName())) seedMockNames();
  var form = setupForm();
  setupTriggers();
  var props = PropertiesService.getScriptProperties();
  Logger.log('──────────────────────────────────────────');
  Logger.log('Form (ส่งให้หมอ):  %s', form.getPublishedUrl());
  Logger.log('Form (แก้ไข):      %s', form.getEditUrl());
  Logger.log('FORM_ID = %s', form.getId());
  if (!props.getProperty('WEB_APP_URL')) {
    Logger.log('⚠ ยังไม่ได้ตั้ง WEB_APP_URL: Deploy ▸ New deployment ▸ Web app (Execute as Me, Anyone) แล้วรัน setWebAppUrl("https://script.google.com/macros/s/.../exec")');
  } else {
    Logger.log('WEB_APP_URL = %s', props.getProperty('WEB_APP_URL'));
  }
  Logger.log('ADMIN_EMAIL = %s | REQUIRE_HEAD_APPROVAL = %s | PENDING_DAYS = %s', cfg_('ADMIN_EMAIL') || '(ว่าง)', cfg_('REQUIRE_HEAD_APPROVAL'), cfg_('PENDING_DAYS'));
  Logger.log('──────────────────────────────────────────');
}

function setWebAppUrl(url) {
  if (!url || !/^https:\/\/script\.google\.com\/.+\/exec$/.test(url)) throw new Error('ต้องเป็น URL ที่ลงท้ายด้วย /exec');
  PropertiesService.getScriptProperties().setProperty('WEB_APP_URL', url);
  Logger.log('WEB_APP_URL = %s', url);
}
function setAdminEmail(email) {
  PropertiesService.getScriptProperties().setProperty('ADMIN_EMAIL', email || '');
}
function setRequireHeadApproval(flag) {
  PropertiesService.getScriptProperties().setProperty('REQUIRE_HEAD_APPROVAL', flag ? 'true' : 'false');
}
function setPendingDays(n) {
  PropertiesService.getScriptProperties().setProperty('PENDING_DAYS', String(n));
}

/** สร้าง tab Roster + Swap log ถ้ายังไม่มี (Roster ว่าง → ใส่ mock 2 บัญชี) */
function setupSheets_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var roster = ss.getSheetByName(cfg_('ROSTER_SHEET'));
  if (!roster) {
    roster = ss.insertSheet(cfg_('ROSTER_SHEET'));
    roster.getRange(1, 1, 1, ROSTER_COLS.length).setValues([ROSTER_COLS]).setFontWeight('bold');
    roster.getRange(2, 1, MOCK_ROSTER_.length, 3).setValues(MOCK_ROSTER_);
    roster.setFrozenRows(1);
    Logger.log('สร้าง tab %s พร้อม mock roster %s รายการ — แก้เป็นรายชื่อจริงก่อนใช้งานจริง', cfg_('ROSTER_SHEET'), MOCK_ROSTER_.length);
  }
  var log = ss.getSheetByName(cfg_('LOG_SHEET'));
  if (!log) {
    log = ss.insertSheet(cfg_('LOG_SHEET'));
    log.getRange(1, 1, 1, LOG_COLS.length).setValues([LOG_COLS]).setFontWeight('bold');
    log.setFrozenRows(1);
    Logger.log('สร้าง tab %s', cfg_('LOG_SHEET'));
  }
}

/**
 * สร้าง Google Form จาก Q (หรือเปิดของเดิมถ้า FORM_ID มีอยู่แล้ว) → เชื่อม destination เข้า Sheet นี้
 * อีเมล: ใช้ "Verified" email collection (ผู้ตอบต้อง sign-in Google แต่ **ไม่จำกัด domain** — รองรับ Gmail ผสม @chula.ac.th)
 * ไม่ใช้ setRequireLogin(true) เพราะนั่นคือ "จำกัดเฉพาะผู้ใช้ในองค์กร" ซึ่งจะกัน Gmail ออก
 */
function setupForm() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var props = PropertiesService.getScriptProperties();
  var form = null;
  var existing = props.getProperty('FORM_ID') || CONFIG.FORM_ID;
  if (existing) {
    try { form = FormApp.openById(existing); Logger.log('ใช้ Form เดิม %s', existing); } catch (e) { form = null; }
  }
  if (!form) {
    form = FormApp.create('ER แลกเวร');
    form.setDescription('ยื่นคำขอแลก/ฝากเวร attending ER — ระบบจะตรวจว่าเป็นเจ้าของเวรจริง แล้วส่งอีเมลให้อีกฝ่ายกดตกลง ครบแล้วจึงแก้ตารางเวรให้อัตโนมัติ\n' +
      'แลกได้หลายเวรในคำขอเดียว (สูงสุด ' + MAX_SLOTS + ' เวรต่อฝั่ง) — อีกฝ่ายจะตกลง/ปฏิเสธทั้งชุดในครั้งเดียว\n' +
      'ถ้าไม่กรอกเวรของอีกฝ่าย = ฝากเวร (ยกเวรของคุณให้)');
    form.setConfirmationMessage('ส่งคำขอแล้ว — ระบบจะตรวจสอบและส่งอีเมลผลให้ภายในไม่กี่วินาที');
    form.setLimitOneResponsePerUser(false);
    form.setAllowResponseEdits(false);
    buildQuestions_(form);
    props.setProperty('FORM_ID', form.getId());
    Logger.log('สร้าง Form ใหม่ %s', form.getId());
  }
  // Verified email (2023+ API) — fallback ไป collectEmail ธรรมดา
  try {
    form.setEmailCollectionType(FormApp.EmailCollectionType.VERIFIED);
  } catch (e) {
    Logger.log('setEmailCollectionType ไม่รองรับ (%s) → ใช้ setCollectEmail(true)', e);
    form.setCollectEmail(true);
  }
  // destination → Sheet นี้ (สร้าง tab "การตอบแบบฟอร์ม N")
  var linked = false;
  try { linked = form.getDestinationId() === ss.getId(); } catch (e) { linked = false; }
  if (!linked) form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  return form;
}

function buildQuestions_(form) {
  var names = readRoster_().names;
  if (!names.length) names = ['(Roster ว่าง — รัน refreshFormRoster หลังใส่รายชื่อ)'];

  form.addListItem().setTitle(Q.A_NAME).setChoiceValues(names).setRequired(true);
  form.addListItem().setTitle(Q.B_NAME).setChoiceValues(names).setRequired(true);

  form.addSectionHeaderItem().setTitle('เวรของคุณ (ที่จะยกให้อีกฝ่าย)')
    .setHelpText('กรอกอย่างน้อย 1 เวร — เวรละ 1 block 8 ชั่วโมง แลกข้ามเช้า/บ่าย/ดึกได้');
  for (var i = 1; i <= MAX_SLOTS; i++) {
    form.addDateItem().setTitle(Q.A_DATE(i)).setRequired(i === 1);
    form.addListItem().setTitle(Q.A_SHIFT(i)).setChoiceValues(SWAPPABLE_SHIFTS_).setRequired(i === 1);
  }
  form.addSectionHeaderItem().setTitle('เวรของอีกฝ่าย (ที่คุณจะรับมา)')
    .setHelpText('เว้นว่างทั้งหมด = ฝากเวร (ยกเวรของคุณให้อีกฝ่ายโดยไม่รับเวรกลับ)');
  for (var j = 1; j <= MAX_SLOTS; j++) {
    form.addDateItem().setTitle(Q.B_DATE(j));
    form.addListItem().setTitle(Q.B_SHIFT(j)).setChoiceValues(SWAPPABLE_SHIFTS_);
  }
  form.addParagraphTextItem().setTitle(Q.NOTE);
}

/** Roster เปลี่ยน → อัปเดต dropdown ชื่อใน Form */
function refreshFormRoster() {
  var form = FormApp.openById(cfg_('FORM_ID'));
  var names = readRoster_().names;
  form.getItems(FormApp.ItemType.LIST).forEach(function (it) {
    var t = it.getTitle();
    if (t === Q.A_NAME || t === Q.B_NAME) it.asListItem().setChoiceValues(names);
  });
  Logger.log('อัปเดตรายชื่อใน Form %s ชื่อ', names.length);
}

/** ติดตั้ง trigger: onFormSubmit (spreadsheet) + expirePending (รายวัน 08:00) — ลบของเก่าก่อน */
function setupTriggers() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    var fn = t.getHandlerFunction();
    if (fn === 'onFormSubmit' || fn === 'expirePending') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onFormSubmit').forSpreadsheet(ss).onFormSubmit().create();
  ScriptApp.newTrigger('expirePending').timeBased().everyDays(1).atHour(8).inTimezone('Asia/Bangkok').create();
  Logger.log('ติดตั้ง trigger onFormSubmit + expirePending แล้ว');
}

/** ดู config ปัจจุบัน */
function showConfig() {
  var p = PropertiesService.getScriptProperties().getProperties();
  Logger.log(JSON.stringify(p, null, 2));
}

/**
 * ทดสอบ locateShift_ กับตารางจริงโดยไม่ต้องส่ง Form
 * เช่น debugLocate('2026-09-10', '8.00 - 16.00')
 */
function debugLocate(dateStr, shift) {
  var r = locateShift_(parseFormDate_(dateStr), shift);
  Logger.log(JSON.stringify(r));
  return r;
}

/** ช่องทดสอบ (SETUP.md §5) — ใส่ชื่อ mock ลงตาราง ก.ย. 2569; ทำเฉพาะไฟล์ที่ชื่อขึ้นต้น "Copy of" */
var MOCK_CELLS_ = [
  ['2026-09-10', '8.00 - 16.00 (1)', 'norawit29'],
  ['2026-09-11', '16.00 - 24.00', 'norawit29'],
  ['2026-09-12', '0.00 - 8.00', 'norawit.kij'],
  ['2026-09-14', '8.00 - 16.00 (2)', 'norawit.kij']
];
function seedMockNames() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!/^copy of/i.test(ss.getName())) throw new Error('seedMockNames ใช้ได้เฉพาะไฟล์ทดสอบที่ชื่อขึ้นต้น "Copy of" (ตอนนี้: ' + ss.getName() + ')');
  MOCK_CELLS_.forEach(function (m) {
    var cell = locateShift_(parseFormDate_(m[0]), m[1]);
    if (cell.error) { Logger.log('seed skip %s %s: %s', m[0], m[1], cell.error); return; }
    if (cellHasName_(cell.value, m[2])) return;
    ss.getSheetByName(cell.sheetName).getRange(cell.row, cell.col).setValue(replaceName_(cell.value, baseName_(cell.value), m[2]) || m[2]);
    Logger.log('seed %s %s: "%s" → %s (tab %s)', m[0], m[1], cell.value, m[2], cell.sheetName);
  });
  SpreadsheetApp.flush();
}
