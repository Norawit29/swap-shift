/**
 * app.gs — web app (login + ตารางรวม + เวรฉัน + ประวัติ + ส่งคำขอ)
 *
 * Auth: magic link — Execute-as-Me/Anyone ใช้ Session.getActiveUser() ไม่ได้ (Gmail ผสม chula)
 *   apiRequestLogin(email) → อีเมลลิงก์ ?login=TOKEN → serveApp_ แลกเป็น session token (เก็บใน tab Sessions)
 *   client เก็บ session ใน localStorage แล้วส่งมากับทุก api call
 *
 * API (google.script.run) — ทุกตัวคืน object ธรรมดา; ถ้า session ไม่ถูกต้อง คืน {error:'unauth'}
 */

var SESSIONS_SHEET = 'Sessions';
var LOGIN_TTL_MIN = 15;
var SESSION_TTL_DAYS = 30;
var WEB_MAX_SLOTS = 10;

// ───────────────────────────── serve ─────────────────────────────

function serveApp_(p) {
  var session = '';
  var loginError = '';
  if (p.login) {
    var r = consumeLoginToken_(String(p.login));
    if (r.error) loginError = r.error; else session = r.session;
  }
  var t = HtmlService.createTemplateFromFile('app');
  t.session = session;
  t.loginError = loginError;
  t.appUrl = cfg_('WEB_APP_URL');
  return t.evaluate()
    .setTitle('ER แลกเวร')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// ───────────────────────────── auth ─────────────────────────────

function sessionsSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SESSIONS_SHEET);
  if (!sh) {
    sh = ss.insertSheet(SESSIONS_SHEET);
    sh.getRange(1, 1, 1, 5).setValues([['token', 'email', 'kind', 'created_at', 'expires_at']]).setFontWeight('bold');
    sh.hideSheet();
  }
  return sh;
}

function apiRequestLogin(email) {
  email = String(email || '').trim().toLowerCase();
  if (!email) return { error: 'กรุณากรอกอีเมล' };
  var roster = readRoster_();
  var person = null;
  for (var n in roster.byName) if (roster.byName[n].email === email) person = roster.byName[n];
  if (!person) return { error: 'ไม่พบอีเมลนี้ใน Roster — ติดต่อธุรการ' };
  var tok = token_();
  var now = new Date();
  sessionsSheet_().appendRow([tok, email, 'login', now, new Date(now.getTime() + LOGIN_TTL_MIN * 60000)]);
  var url = cfg_('WEB_APP_URL') + '?login=' + encodeURIComponent(tok);
  sendMail_(email, '[ER แลกเวร] ลิงก์เข้าสู่ระบบ',
    '<p>สวัสดี ' + esc_(person.name) + '</p><p>กดปุ่มด้านล่างเพื่อเข้าสู่ระบบ ER แลกเวร (ลิงก์ใช้ได้ ' + LOGIN_TTL_MIN + ' นาที ครั้งเดียว)</p>' +
    '<p style="margin:20px 0"><a href="' + url + '" style="background:#0f766e;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold">เข้าสู่ระบบ</a></p>' +
    '<p style="color:#666;font-size:12px">ถ้าคุณไม่ได้ขอ ให้ลบอีเมลนี้ทิ้ง</p>');
  return { ok: true, message: 'ส่งลิงก์เข้าสู่ระบบไปที่ ' + email + ' แล้ว (ใช้ได้ ' + LOGIN_TTL_MIN + ' นาที)' };
}

function consumeLoginToken_(tok) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var sh = sessionsSheet_();
    var vals = sh.getDataRange().getValues();
    for (var i = 1; i < vals.length; i++) {
      if (String(vals[i][0]) !== tok || vals[i][2] !== 'login') continue;
      if (new Date(vals[i][4]) < new Date()) { sh.deleteRow(i + 1); return { error: 'ลิงก์หมดอายุ กรุณาขอใหม่' }; }
      var email = String(vals[i][1]);
      sh.deleteRow(i + 1);
      var sess = token_();
      var now = new Date();
      sh.appendRow([sess, email, 'session', now, new Date(now.getTime() + SESSION_TTL_DAYS * 86400000)]);
      return { session: sess };
    }
    return { error: 'ลิงก์ไม่ถูกต้องหรือถูกใช้ไปแล้ว' };
  } finally {
    lock.releaseLock();
  }
}

/** session token → {email, name, role} | null */
function auth_(session) {
  if (!session) return null;
  var cache = CacheService.getScriptCache();
  var email = cache.get('sess:' + session);
  if (!email) {
    var vals = sessionsSheet_().getDataRange().getValues();
    for (var i = 1; i < vals.length; i++) {
      if (String(vals[i][0]) === session && vals[i][2] === 'session' && new Date(vals[i][4]) > new Date()) { email = String(vals[i][1]); break; }
    }
    if (!email) return null;
    cache.put('sess:' + session, email, 21600);
  }
  var roster = readRoster_();
  for (var n in roster.byName) if (roster.byName[n].email === email) return roster.byName[n];
  return null;
}

function apiLogout(session) {
  CacheService.getScriptCache().remove('sess:' + session);
  var sh = sessionsSheet_();
  var vals = sh.getDataRange().getValues();
  for (var i = vals.length - 1; i >= 1; i--) if (String(vals[i][0]) === session) sh.deleteRow(i + 1);
  return { ok: true };
}

/** ลบ token/session หมดอายุ (เรียกจาก expirePending ได้) */
function cleanupSessions_() {
  var sh = sessionsSheet_();
  var vals = sh.getDataRange().getValues();
  var now = new Date();
  for (var i = vals.length - 1; i >= 1; i--) if (new Date(vals[i][4]) < now) sh.deleteRow(i + 1);
}

// ───────────────────────────── API ─────────────────────────────

function apiMe(session) {
  var me = auth_(session);
  if (!me) return { error: 'unauth' };
  var months = listMonths_();
  var today = fmtDate_(new Date()).slice(0, 7);
  var current = months.length ? months[months.length - 1].ym : today;
  months.forEach(function (m) { if (m.ym === today) current = today; });
  return { email: me.email, name: me.name, role: me.role, months: months, currentYm: current,
    shifts: SWAPPABLE_SHIFTS_, roster: readRoster_().names, maxSlots: WEB_MAX_SLOTS };
}

/** tab ทั้งหมดที่เป็นตารางเดือน → [{ym, label, sheetName}] (เดือนละ 1 = tab ขวาสุด) */
function listMonths_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var byYm = {};
  ss.getSheets().forEach(function (sh) {
    var name = normLabel_(sh.getName());
    for (var m = 0; m < 12; m++) {
      var variants = monthNameVariants_(m).map(normLabel_);
      var hit = variants.some(function (v) { return name.indexOf(v) === 0; });
      if (!hit) continue;
      var ym = name.match(/(\d{4})/);
      if (!ym) continue;
      var y = +ym[1]; if (y > 2400) y -= 543;
      var key = y + '-' + (m + 1 < 10 ? '0' : '') + (m + 1);
      byYm[key] = { ym: key, label: THAI_MONTHS_[m] + ' ' + (y + 543), sheetName: sh.getName() };  // ขวาสุดทับ
    }
  });
  return Object.keys(byYm).sort().map(function (k) { return byYm[k]; });
}

/**
 * ตารางเดือนแบบเดียวกับ Excel
 * @return {{ym, sheetName, rows:[{kind, label, shift, cells:[{v, date, day, mine, swappable, owner}]}]}}
 *   kind: title | dow | date | shift | conf | other; cells = คอลัมน์ C..I (จันทร์..อาทิตย์)
 */
function apiSchedule(session, ym) {
  var me = auth_(session);
  if (!me) return { error: 'unauth' };
  var m = ym.match(/^(\d{4})-(\d{2})$/);
  if (!m) return { error: 'เดือนไม่ถูกต้อง' };
  var first = new Date(+m[1], +m[2] - 1, 1);
  var sh = monthSheet_(first);
  if (!sh) return { error: 'ไม่พบตารางเดือน ' + ym };
  var grid = sh.getDataRange().getDisplayValues();
  var rows = [], curDays = null, started = false;
  for (var r = 0; r < grid.length; r++) {
    var label = String(grid[r][1] || '');
    var kind;
    if (r === 0) kind = 'title';
    else if (r === 1) kind = 'dow';
    else if (isDateRow_(label)) { kind = 'date'; started = true; }
    else if (shiftRowLabel_(label)) kind = 'shift';
    else if (normLabel_(label).indexOf('conference') === 0) kind = 'conf';
    else if (started) break;      // จบ block ตาราง (เช่น แถว Rotation ด้านล่าง)
    else kind = 'other';
    if (kind === 'date') curDays = [];
    var cells = [];
    for (var c = colIndex_(0); c <= colIndex_(6); c++) {
      var v = String(grid[r][c] || '');
      var cell = { v: v };
      if (kind === 'date') {
        var day = parseDayCell_(v);
        curDays[c] = day;
        cell.day = day;
        if (day) cell.date = fmtDate_(new Date(first.getFullYear(), first.getMonth(), day));
      } else if (kind === 'shift' && curDays && curDays[c]) {
        cell.date = fmtDate_(new Date(first.getFullYear(), first.getMonth(), curDays[c]));
        cell.owner = baseName_(v) || '';
        cell.swappable = !!cell.owner;
        cell.mine = cellHasName_(v, me.name);
      }
      cells.push(cell);
    }
    rows.push({ kind: kind, label: label, shift: kind === 'shift' ? shiftDisplayLabel_(label) : null, cells: cells });
  }
  return { ym: ym, sheetName: sh.getName(), title: String(grid[0][1] || ''), rows: rows, me: me.name };
}

function apiMyShifts(session, ym) {
  var s = apiSchedule(session, ym);
  if (s.error) return s;
  var out = [];
  s.rows.forEach(function (row) {
    if (row.kind !== 'shift') return;
    row.cells.forEach(function (c, i) {
      if (c.mine) out.push({ date: c.date, shift: row.shift, dow: i, dateThai: fmtDateThai_(parseFormDate_(c.date)) });
    });
  });
  out.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
  return { ym: ym, shifts: out };
}

function apiHistory(session) {
  var me = auth_(session);
  if (!me) return { error: 'unauth' };
  var out = readLog_().filter(function (rec) {
    return rec.row.a_name === me.name || rec.row.b_name === me.name;
  }).map(function (rec) {
    var r = rec.row;
    var fmt = function (str) { return parseShifts_(str).map(function (x) { return { date: fmtDate_(x.date), dateThai: fmtDateThai_(x.date), shift: x.shift }; }); };
    return { swap_id: r.swap_id, created_at: fmtDateTime_(r.created_at), updated_at: fmtDateTime_(r.updated_at),
      status: r.status, statusThai: statusThai_(r.status), type: r.type,
      a_name: r.a_name, b_name: r.b_name, a_shifts: fmt(r.a_shifts), b_shifts: fmt(r.b_shifts),
      note: r.note, message: r.message, mine: r.a_name === me.name ? 'a' : 'b' };
  });
  out.reverse();
  return { history: out };
}

/**
 * ส่งคำขอจากหน้าเว็บ — ใช้ path เดียวกับ Form (processSubmission_)
 * @param {{bName:string, aShifts:[{date,shift}], bShifts:[{date,shift}], note:string}} payload
 */
function apiSubmit(session, payload) {
  var me = auth_(session);
  if (!me) return { error: 'unauth' };
  payload = payload || {};
  var named = {};
  named[Q.A_NAME] = [me.name];
  named[Q.B_NAME] = [String(payload.bName || '')];
  named[Q.NOTE] = [String(payload.note || '')];
  (payload.aShifts || []).slice(0, WEB_MAX_SLOTS).forEach(function (s, i) { named[Q.A_DATE(i + 1)] = [s.date]; named[Q.A_SHIFT(i + 1)] = [s.shift]; });
  (payload.bShifts || []).slice(0, WEB_MAX_SLOTS).forEach(function (s, i) { named[Q.B_DATE(i + 1)] = [s.date]; named[Q.B_SHIFT(i + 1)] = [s.shift]; });
  var row = processSubmission_(named, me.email, WEB_MAX_SLOTS, 'web');
  if (row.status === 'error') return { error: row.message, swap_id: row.swap_id };
  return { ok: true, swap_id: row.swap_id, b_email: row.b_email };
}

function fmtDateTime_(d) {
  if (!(d instanceof Date)) d = new Date(d);
  if (isNaN(d.getTime())) return '';
  return Utilities.formatDate(d, 'Asia/Bangkok', 'd MMM yy HH:mm');
}
