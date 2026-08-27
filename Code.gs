/**
 * Code.gs — ER shift-swap workflow (bound to ตารางเวรstaff_ปี2569)
 *
 * State machine (ห้ามเปลี่ยน):
 *   pending_b → (pending_head) → committed | rejected | expired | error
 *
 * คำขอ 1 รายการ = เวรของ A หลาย block (สูงสุด MAX_SLOTS) ↔ เวรของ B หลาย block
 * B ตอบรับครั้งเดียว → เขียนทุกช่องพร้อมกัน (validate ทุกช่องก่อนเขียนช่องแรก)
 * ถ้าฝั่ง B ว่าง = ฝากเวร (ยก A ทั้งหมดให้ B)
 *
 * Pure helpers อยู่ใน lib.gs, setup functions อยู่ใน setup.gs
 */

var CONFIG = {
  // ค่า fallback — ค่าจริงอ่านจาก Script Properties key เดียวกัน (ดู cfg_)
  FORM_ID: '',
  WEB_APP_URL: '',
  ADMIN_EMAIL: '',                // ธุรการ (cc ทุก commit / error) — ว่างได้
  REQUIRE_HEAD_APPROVAL: 'false', // 'true' → หลัง B approve ต้องให้ head (Roster บทบาท=head) approve อีกชั้น
  PENDING_DAYS: '3',              // คำขอค้างเกินกี่วัน → expired
  ROSTER_SHEET: 'Roster',
  LOG_SHEET: 'Swap log'
};
var MAX_SLOTS = 4;

function cfg_(key) {
  var v = PropertiesService.getScriptProperties().getProperty(key);
  return (v !== null && v !== undefined && v !== '') ? v : (CONFIG[key] || '');
}

/** หัวข้อคำถามใน Form — setup.gs สร้าง Form จาก object นี้ และ onFormSubmit อ่าน namedValues ด้วย key เดียวกัน */
var Q = {
  EMAIL: ['Email Address', 'ที่อยู่อีเมล', 'อีเมล'],
  A_NAME: 'ชื่อคุณ (ผู้ขอ — ตามชื่อในตารางเวร)',
  B_NAME: 'ชื่ออีกฝ่าย (ตามชื่อในตารางเวร)',
  A_DATE: function (i) { return 'เวรของคุณ #' + i + ' — วันที่'; },
  A_SHIFT: function (i) { return 'เวรของคุณ #' + i + ' — เวร'; },
  B_DATE: function (i) { return 'เวรของอีกฝ่าย #' + i + ' — วันที่'; },
  B_SHIFT: function (i) { return 'เวรของอีกฝ่าย #' + i + ' — เวร'; },
  NOTE: 'หมายเหตุ'
};

var LOG_COLS = ['swap_id', 'created_at', 'updated_at', 'status', 'type',
  'a_name', 'a_email', 'a_shifts',
  'b_name', 'b_email', 'b_shifts',
  'note', 'token_b', 'token_head', 'head_email', 'sheets', 'message', 'source'];

var ROSTER_COLS = ['ชื่อในตาราง', 'อีเมล', 'บทบาท'];

var THAI_MONTHS_SHORT_ = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];

// ───────────────────────────── Form submit ─────────────────────────────

/** Installable trigger: Spreadsheet ▸ onFormSubmit (ติดตั้งโดย setupTriggers) */
function onFormSubmit(e) {
  var named = (e && e.namedValues) || {};
  processSubmission_(named, nv_(named, Q.EMAIL).toLowerCase(), MAX_SLOTS, 'form');
}

/**
 * จุดร่วมของ Form และ web app: สร้างคำขอจาก namedValues (key ตาม Q) + อีเมลที่ยืนยันแล้ว
 * @return {{swap_id, status, message}} แถว log ที่สร้าง
 */
function processSubmission_(named, verifiedEmail, maxSlots, source) {
  var req = {
    email: String(verifiedEmail || '').toLowerCase(),
    aName: baseName_(nv_(named, [Q.A_NAME])),
    bName: baseName_(nv_(named, [Q.B_NAME])),
    note: nv_(named, [Q.NOTE])
  };
  var aSlots = readShiftSlots_(named, maxSlots, function (i) { return [Q.A_DATE(i)]; }, function (i) { return [Q.A_SHIFT(i)]; });
  var bSlots = readShiftSlots_(named, maxSlots, function (i) { return [Q.B_DATE(i)]; }, function (i) { return [Q.B_SHIFT(i)]; });
  req.aShifts = aSlots.error ? [] : aSlots;
  req.bShifts = bSlots.error ? [] : bSlots;
  req.slotError = aSlots.error ? ('เวรของคุณ: ' + aSlots.error) : (bSlots.error ? ('เวรของอีกฝ่าย: ' + bSlots.error) : '');
  req.isSwap = req.bShifts.length > 0;

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var roster = readRoster_();
    var v = validateRequest_(req, roster);
    var id = nextSwapId_();
    var now = new Date();
    var row = {
      swap_id: id, created_at: now, updated_at: now,
      type: req.isSwap ? 'swap' : 'give',
      a_name: req.aName, a_email: req.email, a_shifts: serializeShifts_(req.aShifts),
      b_name: req.bName, b_email: v.bEmail || '', b_shifts: serializeShifts_(req.bShifts),
      note: req.note, token_b: '', token_head: '', head_email: '', sheets: (v.sheets || []).join(', '),
      message: '', source: source || 'form'
    };
    if (v.error) {
      row.status = 'error';
      row.message = v.error;
      appendLog_(row);
      if (req.email && source !== 'web') {   // web ได้ผลทันทีบนหน้าจอ ไม่ต้องส่งอีเมล
        sendMail_(req.email, '[ER แลกเวร] คำขอ ' + id + ' ไม่ผ่านการตรวจสอบ',
          '<p>คำขอของคุณไม่ผ่านการตรวจสอบ:</p><p><b>' + esc_(v.error) + '</b></p>' + summaryHtml_(row) +
          '<p>กรุณาตรวจสอบตารางเวรแล้วส่งใหม่</p>');
      }
      return row;
    }
    row.status = 'pending_b';
    row.token_b = token_();
    appendLog_(row);
    var base = cfg_('WEB_APP_URL');
    var kind = req.isSwap ? 'แลกเวร' : 'ฝากเวร';
    sendMail_(row.b_email, '[ER แลกเวร] ' + row.a_name + ' ขอ' + kind + 'กับคุณ (' + id + ')',
      '<p>' + esc_(row.a_name) + ' ส่งคำขอ' + kind + 'ถึงคุณ กรุณาตรวจสอบแล้วกดตกลง/ปฏิเสธ <b>ครั้งเดียวสำหรับทุกเวรในคำขอนี้</b></p>' + summaryHtml_(row) +
      buttonsHtml_(link_(base, id, row.token_b, 'approve', 'b'), link_(base, id, row.token_b, 'reject', 'b')) +
      '<p style="color:#666">ลิงก์ใช้ได้ครั้งเดียว และหมดอายุใน ' + esc_(cfg_('PENDING_DAYS')) + ' วัน — ถ้าไม่ตอบ คำขอจะถูกยกเลิกอัตโนมัติ</p>');
    sendMail_(row.a_email, '[ER แลกเวร] ส่งคำขอ ' + id + ' ให้ ' + row.b_name + ' แล้ว',
      '<p>ระบบส่งคำขอของคุณให้ ' + esc_(row.b_name) + ' แล้ว รอการตอบรับ</p>' + summaryHtml_(row));
    return row;
  } finally {
    lock.releaseLock();
  }
}

/**
 * ตรวจคำขอ: อีเมล verified ตรง Roster, ทุกเวรเป็นของเจ้าตัวจริง ณ ตอนนี้, ไม่มีคำขอค้างซ้อนช่องเดียวกัน
 * @return {{error?:string, bEmail?:string, aCells?:Object[], bCells?:Object[], sheets?:string[]}}
 */
function validateRequest_(req, roster) {
  if (!req.email) return { error: 'Form ไม่ได้ส่งอีเมล (ต้องเปิด Collect email แบบ Verified)' };
  var a = roster.byName[req.aName];
  if (!a) return { error: 'ไม่พบชื่อ "' + req.aName + '" ใน Roster' };
  if (a.email !== req.email) {
    return { error: 'อีเมลที่ส่ง Form (' + req.email + ') ไม่ตรงกับอีเมลของ ' + req.aName + ' ใน Roster' };
  }
  var b = roster.byName[req.bName];
  if (!b) return { error: 'ไม่พบชื่อ "' + req.bName + '" ใน Roster' };
  var out = { bEmail: b.email };
  if (req.aName === req.bName) return err_(out, 'ผู้ขอกับอีกฝ่ายเป็นคนเดียวกัน');
  if (req.slotError) return err_(out, req.slotError);
  if (!req.aShifts.length) return err_(out, 'ต้องระบุเวรของคุณอย่างน้อย 1 เวร');

  var located = locateOwned_(req.aName, req.aShifts, 'เวรของคุณ');
  if (located.error) return err_(out, located.error);
  out.aCells = located.cells;
  out.bCells = [];
  if (req.isSwap) {
    var lb = locateOwned_(req.bName, req.bShifts, 'เวรของอีกฝ่าย');
    if (lb.error) return err_(out, lb.error);
    out.bCells = lb.cells;
  }
  var all = out.aCells.concat(out.bCells), seen = {};
  for (var i = 0; i < all.length; i++) {
    if (seen[all[i].key]) return err_(out, 'ระบุเวรซ้ำกัน: ' + all[i].label);
    seen[all[i].key] = true;
  }
  var dup = findPendingOnCells_(all);
  if (dup) return err_(out, 'มีคำขอ ' + dup + ' ที่ยังรอตอบรับอยู่บนเวรเดียวกัน — รอให้เสร็จหรือหมดอายุก่อน');
  out.sheets = all.map(function (c) { return c.sheetName; }).filter(function (v, i, arr) { return arr.indexOf(v) === i; });
  return out;
}

function err_(out, msg) { out.error = msg; return out; }

/** หา cell ของทุกเวรใน list และยืนยันว่าเป็นของ name → {cells} | {error} */
function locateOwned_(name, shifts, what) {
  var cells = [];
  for (var i = 0; i < shifts.length; i++) {
    var s = shifts[i];
    var cell = locateShift_(s.date, s.shift);
    var label = fmtDateThai_(s.date) + ' ' + s.shift;
    if (cell.error) return { error: what + ' ' + label + ': ' + cell.error };
    if (!cellHasName_(cell.value, name)) {
      return { error: what + ' ' + label + ' ในตารางตอนนี้เป็นของ "' + (cell.value || '(ว่าง)') + '" ไม่ใช่ ' + name };
    }
    cell.label = label;
    cells.push(cell);
  }
  return { cells: cells };
}

// ───────────────────────────── Web app (approve / reject) ─────────────────────────────

function doGet(e) {
  var p = (e && e.parameter) || {};
  var id = String(p.id || ''), t = String(p.t || ''), action = String(p.a || ''), role = String(p.role || 'b');
  if (!id && !t && !action) return serveApp_(p);   // ไม่มี param = เปิด web app (app.gs)
  if (!id || !t || (action !== 'approve' && action !== 'reject')) return page_('ลิงก์ไม่ถูกต้อง', 'พารามิเตอร์ไม่ครบ');

  // ถือ lock เดียวกับ onFormSubmit/expirePending — กัน B กดสองครั้งเร็วๆ หรือชนกับ commit อื่น
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var rec = findLog_(id);
    if (!rec) return page_('ไม่พบคำขอ', 'ไม่พบคำขอ ' + esc_(id));
    var row = rec.row;
    var expectToken = role === 'head' ? row.token_head : row.token_b;
    var expectStatus = role === 'head' ? 'pending_head' : 'pending_b';
    if (row.status !== expectStatus) {
      return page_('คำขอนี้ถูกดำเนินการแล้ว', 'คำขอ ' + esc_(id) + ' อยู่ในสถานะ <b>' + esc_(statusThai_(row.status)) + '</b> แล้ว ไม่สามารถทำซ้ำได้');
    }
    if (!expectToken || t !== expectToken) return page_('ลิงก์ไม่ถูกต้อง', 'token ไม่ตรง');

    if (action === 'reject') {
      updateLog_(rec, { status: 'rejected', message: (role === 'head' ? 'head' : row.b_name) + ' ปฏิเสธ', token_b: '', token_head: '' });
      sendMail_(row.a_email, '[ER แลกเวร] คำขอ ' + id + ' ถูกปฏิเสธ',
        '<p>' + esc_(role === 'head' ? 'หัวหน้า' : row.b_name) + ' ปฏิเสธคำขอของคุณ ตารางเวรไม่ถูกแก้</p>' + summaryHtml_(row));
      return page_('ปฏิเสธคำขอแล้ว', 'บันทึกการปฏิเสธคำขอ ' + esc_(id) + ' แล้ว ระบบแจ้ง ' + esc_(row.a_name) + ' ทางอีเมล');
    }

    // approve
    if (role === 'b' && cfg_('REQUIRE_HEAD_APPROVAL') === 'true') {
      var heads = readRoster_().heads;
      if (!heads.length) {
        updateLog_(rec, { status: 'error', message: 'REQUIRE_HEAD_APPROVAL=true แต่ Roster ไม่มีบทบาท head', token_b: '' });
        return page_('เกิดข้อผิดพลาด', 'ไม่พบหัวหน้าใน Roster — แจ้งธุรการ');
      }
      var tokenHead = token_();
      updateLog_(rec, { status: 'pending_head', token_head: tokenHead, head_email: heads.join(','), token_b: '', message: row.b_name + ' ตอบรับแล้ว รอ head' });
      var base = cfg_('WEB_APP_URL');
      sendMail_(heads.join(','), '[ER แลกเวร] ขออนุมัติ ' + id + ' (' + row.a_name + ' ↔ ' + row.b_name + ')',
        '<p>ทั้งสองฝ่ายตกลงแล้ว รอหัวหน้าอนุมัติ</p>' + summaryHtml_(row) +
        buttonsHtml_(link_(base, id, tokenHead, 'approve', 'head'), link_(base, id, tokenHead, 'reject', 'head')));
      return page_('ตอบรับแล้ว', 'บันทึกการตอบรับคำขอ ' + esc_(id) + ' แล้ว ส่งต่อให้หัวหน้าอนุมัติ');
    }

    var res = commitSwap_(rec);
    if (res.error) return page_('เขียนตารางไม่สำเร็จ', esc_(res.error) + '<br>ระบบแจ้งทุกฝ่ายทางอีเมลแล้ว');
    return page_('แลกเวรสำเร็จ', 'เขียนคำขอ ' + esc_(id) + ' ลงตารางเวรแล้ว (' + res.n + ' ช่อง) ระบบแจ้งทั้งสองฝ่ายทางอีเมล');
  } finally {
    lock.releaseLock();
  }
}

/**
 * เขียนลงตารางหลัก — re-validate ทุกช่องก่อนเขียนช่องแรกเสมอ (ตารางอาจถูกแก้ระหว่างรอ)
 * ต้องเรียกภายใต้ lock
 */
function commitSwap_(rec) {
  var row = rec.row;
  try {
    var la = locateOwned_(row.a_name, parseShifts_(row.a_shifts), 'เวรของ ' + row.a_name);
    if (la.error) throw new Error(la.error + ' (ตารางถูกแก้ระหว่างรอ?)');
    var lb = { cells: [] };
    if (row.type === 'swap') {
      lb = locateOwned_(row.b_name, parseShifts_(row.b_shifts), 'เวรของ ' + row.b_name);
      if (lb.error) throw new Error(lb.error + ' (ตารางถูกแก้ระหว่างรอ?)');
    }
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var writes = la.cells.map(function (c) { return { c: c, v: replaceName_(c.value, row.a_name, row.b_name) }; })
      .concat(lb.cells.map(function (c) { return { c: c, v: replaceName_(c.value, row.b_name, row.a_name) }; }));
    writes.forEach(function (w) { ss.getSheetByName(w.c.sheetName).getRange(w.c.row, w.c.col).setValue(w.v); });
    SpreadsheetApp.flush();
    updateLog_(rec, { status: 'committed', message: 'เขียนตารางแล้ว ' + writes.length + ' ช่อง', token_b: '', token_head: '' });
    var to = [row.a_email, row.b_email].filter(Boolean).join(',');
    sendMail_(to, '[ER แลกเวร] ' + row.swap_id + ' สำเร็จ — ตารางเวรถูกแก้แล้ว',
      '<p>ระบบแก้ตารางเวรตามคำขอนี้เรียบร้อยแล้ว (' + writes.length + ' ช่อง, tab ' + esc_(row.sheets) + ')</p>' + summaryHtml_(row), cfg_('ADMIN_EMAIL'));
    return { ok: true, n: writes.length };
  } catch (err) {
    var msg = String(err && err.message || err);
    updateLog_(rec, { status: 'error', message: msg, token_b: '', token_head: '' });
    var to2 = [row.a_email, row.b_email, cfg_('ADMIN_EMAIL')].filter(Boolean).join(',');
    sendMail_(to2, '[ER แลกเวร] ' + row.swap_id + ' เขียนตารางไม่สำเร็จ',
      '<p style="color:#b00">' + esc_(msg) + '</p>' + summaryHtml_(row) + '<p>ตารางไม่ถูกแก้แม้แต่ช่องเดียว กรุณาตรวจตารางแล้วส่งคำขอใหม่ หรือติดต่อธุรการ</p>');
    return { error: msg };
  }
}

// ───────────────────────────── Expire (time trigger) ─────────────────────────────

/**
 * รายวัน: pending_b / pending_head ที่ updated_at เก่ากว่า PENDING_DAYS → expired
 * ใช้ updated_at เป็นฐาน (ตั้งใจ): เมื่อ B approve แล้วเข้า pending_head นาฬิกาจะเริ่มใหม่ให้ head มีเวลาเต็ม
 * @param {number=} daysOverride ใช้ตอนทดสอบ เช่น expirePending(0)
 */
function expirePending(daysOverride) {
  var days = (typeof daysOverride === 'number') ? daysOverride : Number(cfg_('PENDING_DAYS')) || 3;
  var cutoff = new Date(Date.now() - days * 86400000);
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var n = 0;
    readLog_().forEach(function (rec) {
      var row = rec.row;
      if (row.status !== 'pending_b' && row.status !== 'pending_head') return;
      var upd = row.updated_at instanceof Date ? row.updated_at : new Date(row.updated_at);
      if (isNaN(upd.getTime()) || upd > cutoff) return;
      updateLog_(rec, { status: 'expired', message: 'ไม่มีการตอบรับภายใน ' + days + ' วัน', token_b: '', token_head: '' });
      var to = [row.a_email, row.b_email].filter(Boolean).join(',');
      sendMail_(to, '[ER แลกเวร] คำขอ ' + row.swap_id + ' หมดอายุ',
        '<p>คำขอนี้ไม่ได้รับการตอบรับภายใน ' + days + ' วัน ระบบยกเลิกให้แล้ว ตารางเวรไม่ถูกแก้</p>' + summaryHtml_(row));
      n++;
    });
    cleanupSessions_();
    Logger.log('expirePending: %s expired', n);
    return n;
  } finally {
    lock.releaseLock();
  }
}

// ───────────────────────────── Sheet access ─────────────────────────────

/**
 * หา tab ของเดือน — ไฟล์จริงมี 'กันยายน2569' และ revision 'กันยายน2569 (แลก1..N)'
 * เลือก tab ที่ match ชื่อเดือน+ปี ที่อยู่ **ขวาสุด** (= revision ล่าสุด)
 * override ได้ด้วย Script Property TAB_<YYYY-MM> เช่น TAB_2026-09 = 'กันยายน2569 (แลก5)'
 */
function monthSheet_(date) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ym = fmtDate_(date).slice(0, 7);
  var override = PropertiesService.getScriptProperties().getProperty('TAB_' + ym);
  if (override) return ss.getSheetByName(override);

  var my = thaiMonthYear_(date);
  var variants = monthNameVariants_(date.getMonth()).concat([THAI_MONTHS_SHORT_[date.getMonth()]]).map(normLabel_);
  var yearStrs = [String(my.yearBE), String(date.getFullYear())];
  var skip = [normLabel_(cfg_('ROSTER_SHEET')), normLabel_(cfg_('LOG_SHEET'))];
  var best = null, bestNoYear = null;
  ss.getSheets().forEach(function (sh) {
    var name = normLabel_(sh.getName());
    if (skip.indexOf(name) >= 0) return;
    var hasMonth = variants.some(function (v) { return name.indexOf(v) >= 0; });
    if (!hasMonth) return;
    var hasYear = yearStrs.some(function (y) { return name.indexOf(y) >= 0; });
    if (hasYear) best = sh; else bestNoYear = sh;   // ไม่ break → ได้ตัวขวาสุด
  });
  return best || bestNoYear || null;
}

/**
 * หา cell ของเวรในตารางจริง
 * @return {{sheetName, row, col, value, key}|{error}}  row/col เป็น 1-based สำหรับ getRange
 */
function locateShift_(date, shiftLabel) {
  if (!date) return { error: 'วันที่ไม่ถูกต้อง' };
  var rowLabel = shiftRowLabel_(shiftLabel);
  if (!rowLabel) return { error: 'เวร "' + shiftLabel + '" แลกไม่ได้' };
  var sh = monthSheet_(date);
  if (!sh) return { error: 'ไม่พบ tab ของเดือน ' + thaiMonthYear_(date).month + ' ' + thaiMonthYear_(date).yearBE };
  var grid = sh.getDataRange().getDisplayValues();
  var labels = grid.map(function (r) { return r[1]; });
  var hit = findShiftInGrid_(labels, grid, date.getDate(), rowLabel, dowMon0_(date));
  if (hit.error) return { error: hit.error + ' (tab ' + sh.getName() + ')' };
  return { sheetName: sh.getName(), row: hit.r + 1, col: hit.c + 1, value: grid[hit.r][hit.c], key: shiftKey_(date, shiftLabel) };
}

function readRoster_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(cfg_('ROSTER_SHEET'));
  if (!sh) throw new Error('ไม่พบ tab ' + cfg_('ROSTER_SHEET') + ' — รัน setupAll ก่อน');
  var vals = sh.getDataRange().getValues();
  var byName = {}, heads = [], names = [];
  for (var i = 1; i < vals.length; i++) {
    var name = baseName_(vals[i][0]), email = String(vals[i][1] || '').trim().toLowerCase(), role = String(vals[i][2] || '').trim().toLowerCase();
    if (!name || !email) continue;
    byName[name] = { name: name, email: email, role: role };
    names.push(name);
    if (role === 'head') heads.push(email);
  }
  return { byName: byName, heads: heads, names: names };
}

function logSheet_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(cfg_('LOG_SHEET'));
  if (!sh) throw new Error('ไม่พบ tab ' + cfg_('LOG_SHEET') + ' — รัน setupAll ก่อน');
  return sh;
}

/** ต้องเรียกภายใต้ lock */
function nextSwapId_() {
  var n = Math.max(logSheet_().getLastRow() - 1, 0) + 1;
  return 'SW' + fmtDate_(new Date()).replace(/-/g, '') + '-' + ('000' + n).slice(-4);
}

/** ต้องเรียกภายใต้ lock */
function appendLog_(row) {
  logSheet_().appendRow(LOG_COLS.map(function (k) { return row[k] === undefined ? '' : row[k]; }));
  SpreadsheetApp.flush();
}

function readLog_() {
  var vals = logSheet_().getDataRange().getValues();
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    var row = {};
    LOG_COLS.forEach(function (k, j) { row[k] = vals[i][j]; });
    if (row.swap_id) out.push({ rowNum: i + 1, row: row });
  }
  return out;
}

function findLog_(id) {
  var recs = readLog_();
  for (var i = 0; i < recs.length; i++) if (String(recs[i].row.swap_id) === id) return recs[i];
  return null;
}

function updateLog_(rec, patch) {
  patch.updated_at = new Date();
  for (var k in patch) rec.row[k] = patch[k];
  logSheet_().getRange(rec.rowNum, 1, 1, LOG_COLS.length)
    .setValues([LOG_COLS.map(function (k) { return rec.row[k] === undefined ? '' : rec.row[k]; })]);
  SpreadsheetApp.flush();
}

/** มีคำขอ pending บนเวรใดในรายการหรือไม่ → คืน swap_id หรือ null (cells[i].key = shiftKey_) */
function findPendingOnCells_(cells) {
  var keys = {};
  cells.forEach(function (c) { keys[c.key] = true; });
  var recs = readLog_();
  for (var i = 0; i < recs.length; i++) {
    var row = recs[i].row;
    if (row.status !== 'pending_b' && row.status !== 'pending_head') continue;
    var pend = parseShifts_(row.a_shifts).concat(parseShifts_(row.b_shifts));
    for (var p = 0; p < pend.length; p++) {
      if (keys[shiftKey_(pend[p].date, pend[p].shift)]) return row.swap_id;
    }
  }
  return null;
}

// ───────────────────────────── Email / HTML helpers ─────────────────────────────

function token_() {
  return Utilities.getUuid().replace(/-/g, '') + randomToken_(8);
}

function link_(base, id, token, action, role) {
  if (!base) return '(ยังไม่ได้ตั้ง WEB_APP_URL — รัน setWebAppUrl)';
  return base + '?id=' + encodeURIComponent(id) + '&t=' + encodeURIComponent(token) + '&a=' + action + '&role=' + role;
}

function sendMail_(to, subject, html, cc) {
  if (!to) return;
  var footer = '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;border-collapse:collapse">' +
    '<tr><td style="padding:18px 8px 28px;border-top:1px solid #e3e8ee;font-family:Sarabun,Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;color:#8a97a8;text-align:center">' +
    '<span style="color:#0f766e;font-weight:700">ER แลกเวร</span> &middot; อีเมลอัตโนมัติ กรุณาอย่าตอบกลับ</td></tr></table>';
  var opt = { to: to, subject: subject, htmlBody: '<div style="background:#f4f7fa;padding:8px 0">' + html + footer + '</div>', name: 'ER แลกเวร' };
  if (cc) opt.cc = cc;
  try { MailApp.sendEmail(opt); } catch (err) { Logger.log('sendMail failed to %s: %s', to, err); }
}

function shiftListHtml_(str) {
  var list = parseShifts_(str);
  var font = 'font-family:Sarabun,Arial,Helvetica,sans-serif;';
  if (!list.length) return '<span style="' + font + 'font-size:14px;color:#9aa7b5;font-style:italic">(ไม่มี)</span>';
  return '<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%">' + list.map(function (x) {
    return '<tr><td style="padding:4px 0">' +
      '<div style="' + font + 'font-size:14px;line-height:20px;color:#1e293b;font-weight:600">' + esc_(fmtDateThai_(x.date)) + '</div>' +
      '<div style="' + font + 'font-size:13px;line-height:18px;color:#475569">&#9201; ' + esc_(x.shift) + '</div></td></tr>';
  }).join('') + '</table>';
}

function summaryHtml_(row) {
  var give = row.type === 'give';
  var font = 'font-family:Sarabun,Arial,Helvetica,sans-serif;';
  var col = function (name, arrowText, target, shifts) {
    return '<td width="50%" valign="top" style="padding:14px 16px;vertical-align:top;background:#ffffff">' +
      '<div style="' + font + 'font-size:11px;line-height:16px;letter-spacing:.6px;text-transform:uppercase;color:#64748b;font-weight:700">เวรของ</div>' +
      '<div style="' + font + 'font-size:17px;line-height:24px;color:#0f172a;font-weight:700">' + esc_(name) + '</div>' +
      '<div style="' + font + 'font-size:13px;line-height:18px;color:#0f766e;font-weight:600;margin:2px 0 10px">&#8594; ' + arrowText + ' ' + esc_(target) + '</div>' +
      shiftListHtml_(shifts) + '</td>';
  };
  var h = '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:16px auto;border-collapse:separate;border:1px solid #dbe3ec;border-radius:12px;overflow:hidden;background:#ffffff">' +
    '<tr><td style="padding:14px 16px;background:#f0f7f7;border-bottom:1px solid #dbe3ec">' +
      '<table role="presentation" cellpadding="0" cellspacing="0"><tr>' +
      '<td style="' + font + 'font-size:12px;line-height:18px;color:#0f766e;background:#ffffff;border:1px solid #99d5cf;border-radius:6px;padding:2px 8px;font-weight:700;font-family:Menlo,Consolas,monospace">' + esc_(row.swap_id) + '</td>' +
      '<td style="width:8px"></td>' +
      '<td style="' + font + 'font-size:12px;line-height:18px;color:#ffffff;background:' + (give ? '#7c3aed' : '#0f766e') + ';border-radius:999px;padding:2px 12px;font-weight:700">' + (give ? 'ฝากเวร (ยกให้)' : 'แลกเวร') + '</td>' +
      '</tr></table></td></tr>' +
    '<tr><td style="padding:0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr>' +
      col(row.a_name, give ? 'ยกให้' : 'ไปเป็นของ', row.b_name, row.a_shifts);
  if (!give) h += '<td width="1" style="width:1px;background:#e2e8f0;padding:0"></td>' + col(row.b_name, 'ไปเป็นของ', row.a_name, row.b_shifts);
  h += '</tr></table></td></tr>';
  if (row.note) h += '<tr><td style="padding:12px 16px;border-top:1px solid #dbe3ec;background:#fbfcfd;' + font + 'font-size:13px;line-height:19px;color:#475569">' +
    '<span style="color:#64748b;font-weight:700">หมายเหตุ:</span> ' + esc_(row.note) + '</td></tr>';
  return h + '</table>';
}

function buttonsHtml_(approveUrl, rejectUrl) {
  var font = 'font-family:Sarabun,Arial,Helvetica,sans-serif;';
  var btn = function (url, bg, label) {
    return '<td style="padding:6px 6px"><a href="' + url + '" style="display:block;background:' + bg + ';color:#ffffff;' + font +
      'font-size:16px;line-height:24px;font-weight:700;text-align:center;text-decoration:none;padding:14px 22px;border-radius:10px;min-width:150px">' + label + '</a></td>';
  };
  return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:20px auto 8px;border-collapse:collapse"><tr>' +
    btn(approveUrl, '#15803d', '&#10004; ตกลงทั้งหมด') + btn(rejectUrl, '#b91c1c', '&#10008; ปฏิเสธ') + '</tr></table>';
}

function statusThai_(s) {
  return { pending_b: 'รออีกฝ่ายตอบรับ', pending_head: 'รอหัวหน้าอนุมัติ', committed: 'แลกเวรสำเร็จ',
    rejected: 'ถูกปฏิเสธ', expired: 'หมดอายุ', error: 'ผิดพลาด' }[s] || s;
}

function page_(title, body) {
  var kind = /ปฏิเสธ|ไม่สำเร็จ|ผิดพลาด|ไม่ถูกต้อง|ไม่พบ/.test(title) ? 'error' : (/สำเร็จ|ตอบรับ/.test(title) ? 'success' : 'info');
  var theme = { success: ['#15803d', '#dcfce7', '&#10004;'], error: ['#b91c1c', '#fee2e2', '&#10008;'], info: ['#64748b', '#e2e8f0', '&#8505;'] }[kind];
  var html = '<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>' + esc_(title) + '</title>' +
    '<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;700&display=swap" rel="stylesheet">' +
    '<style>' +
    '*{box-sizing:border-box}html,body{margin:0;padding:0}' +
    'body{font-family:Sarabun,"Noto Sans Thai",-apple-system,"Segoe UI",Roboto,sans-serif;background:#f4f7fa;color:#1e293b;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px 16px}' +
    '.brand{font-size:13px;font-weight:700;letter-spacing:.5px;color:#0f766e;margin-bottom:14px}' +
    '.card{background:#fff;width:100%;max-width:440px;border-radius:16px;box-shadow:0 8px 30px rgba(15,23,42,.08);border:1px solid #e2e8f0;padding:32px 24px;text-align:center}' +
    '.icon{width:72px;height:72px;border-radius:50%;margin:0 auto 18px;display:flex;align-items:center;justify-content:center;font-size:34px;line-height:1;background:' + theme[1] + ';color:' + theme[0] + '}' +
    'h1{font-size:22px;line-height:1.35;margin:0 0 10px;color:#0f172a;font-weight:700}' +
    '.body{font-size:15px;line-height:1.7;color:#475569;margin:0;word-break:break-word}' +
    '.body b{color:#0f172a}' +
    '.hint{font-size:13px;color:#94a3b8;margin-top:22px;padding-top:16px;border-top:1px solid #eef2f6}' +
    '@media (max-width:420px){.card{padding:28px 18px}h1{font-size:20px}}' +
    '</style></head><body>' +
    '<div class="brand">ER แลกเวร</div>' +
    '<div class="card" role="status"><div class="icon" aria-hidden="true">' + theme[2] + '</div>' +
    '<h1>' + esc_(title) + '</h1><p class="body">' + body + '</p>' +
    '<div class="hint">ปิดหน้านี้ได้เลย — ระบบบันทึกผลแล้ว</div></div>' +
    '</body></html>';
  return HtmlService.createHtmlOutput(html).setTitle(title);
}

function esc_(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
