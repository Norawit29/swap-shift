/**
 * lib.gs — pure helpers (ไม่แตะ SpreadsheetApp / FormApp / MailApp)
 * โหลดใน node ได้ผ่าน test/load.js เพื่อ unit test
 */

var THAI_MONTHS_ = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
  'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'];

/**
 * เวรที่แลกได้ (block ละ 8 ชม.) — label ที่ผู้ใช้เห็นใน Form/อีเมล
 * เวรเช้ามี 2 คน: (1) = แถว '8.00 - 16.00', (2) = แถว 'On floor 1-2' ในตาราง
 */
var SWAPPABLE_SHIFTS_ = ['8.00 - 16.00 (1)', '8.00 - 16.00 (2)', '16.00 - 24.00', '0.00 - 8.00'];

/** label ใน Form → label แถวในตาราง (key = normLabel_) */
var SHIFT_ROW_MAP_ = {
  '8.00-16.00(1)': '8.00 - 16.00',
  '8.00-16.00(2)': 'On floor 1-2',
  '16.00-24.00': '16.00 - 24.00',
  '0.00-8.00': '0.00 - 8.00',
  // รองรับ label เก่า / พิมพ์ตรงกับแถว
  '8.00-16.00': '8.00 - 16.00',
  'onfloor1-2': 'On floor 1-2'
};

/** label ใน Form → label แถวในตาราง หรือ null ถ้าแลกไม่ได้ */
function shiftRowLabel_(formLabel) {
  return SHIFT_ROW_MAP_[normLabel_(formLabel)] || null;
}

/** label แถวในตาราง → label ที่แสดงผล */
function shiftDisplayLabel_(rowLabel) {
  var n = normLabel_(rowLabel);
  for (var i = 0; i < SWAPPABLE_SHIFTS_.length; i++) {
    if (normLabel_(SHIFT_ROW_MAP_[normLabel_(SWAPPABLE_SHIFTS_[i])]) === n) return SWAPPABLE_SHIFTS_[i];
  }
  return rowLabel;
}

/** สะกดชื่อเดือนแบบอื่นที่พบใน tab จริง */
var THAI_MONTH_ALIASES_ = { 'กรกฎาคม': ['กรกฏาคม'] };

var DATE_ROW_LABEL_ = 'วันที่';

/**
 * รับค่าวันที่จาก Form ได้หลายรูปแบบ:
 *   Date object, 'YYYY-MM-DD', 'DD/MM/YYYY', 'D/M/YYYY', 'YYYY-MM-DD HH:mm:ss'
 * คืน Date (local midnight) หรือ null ถ้า parse ไม่ได้
 */
function parseFormDate_(v) {
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return null;
    return new Date(v.getFullYear(), v.getMonth(), v.getDate());
  }
  if (v === null || v === undefined) return null;
  var s = String(v).trim();
  if (!s) return null;
  var m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return mkDate_(+m[1], +m[2], +m[3]);
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) {
    var y = +m[3];
    if (y > 2400) y -= 543; // เผื่อกรอกเป็น พ.ศ.
    return mkDate_(y, +m[2], +m[1]);
  }
  return null;
}

function mkDate_(y, mo, d) {
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  var dt = new Date(y, mo - 1, d);
  if (dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
  return dt;
}

/** 'YYYY-MM-DD' */
function fmtDate_(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  var mo = d.getMonth() + 1, day = d.getDate();
  return d.getFullYear() + '-' + (mo < 10 ? '0' : '') + mo + '-' + (day < 10 ? '0' : '') + day;
}

/** 'พฤ. 10 กันยายน 2569' สำหรับอีเมล */
function fmtDateThai_(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return '';
  var dow = ['อา.', 'จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.'][d.getDay()];
  return dow + ' ' + d.getDate() + ' ' + THAI_MONTHS_[d.getMonth()] + ' ' + (d.getFullYear() + 543);
}

/** ชื่อเดือนไทย + ปี พ.ศ. ของวันที่ เช่น {month:'กันยายน', yearBE:2569} */
function thaiMonthYear_(d) {
  return { month: THAI_MONTHS_[d.getMonth()], yearBE: d.getFullYear() + 543 };
}

/** normalize label: lowercase, ตัด whitespace ทั้งหมด, ตัด '*' / ':' */
function normLabel_(s) {
  return String(s === null || s === undefined ? '' : s)
    .toLowerCase()
    .replace(/[\s ]+/g, '')
    .replace(/[*:：]/g, '');
}

/** ชื่อในช่อง ตัด suffix ' TM' และ whitespace */
function baseName_(cell) {
  return String(cell === null || cell === undefined ? '' : cell)
    .replace(/[\s ]+/g, ' ')
    .trim()
    .replace(/\s*TM\s*$/i, '')
    .trim();
}

/** ช่องนี้เป็นเวรของ name หรือไม่ (ignore suffix TM / whitespace) */
function cellHasName_(cell, name) {
  var b = baseName_(cell), n = baseName_(name);
  if (!b || !n) return false;
  return b === n;
}

/**
 * แทนชื่อ oldName ด้วย newName ในช่อง โดยรักษา suffix ' TM' ไว้
 * ถ้าช่องไม่ใช่ของ oldName คืนค่าเดิม
 */
function replaceName_(cell, oldName, newName) {
  if (!cellHasName_(cell, oldName)) return cell;
  var s = String(cell).replace(/[\s ]+/g, ' ').trim();
  var hasTM = /\s*TM\s*$/i.test(s);
  return baseName_(newName) + (hasTM ? ' TM' : '');
}

/** วันในสัปดาห์ (0=จันทร์ … 6=อาทิตย์) → index คอลัมน์ในแถว (A=0, B=1, C=2 … I=8) */
function colIndex_(dowMon0) {
  if (dowMon0 < 0 || dowMon0 > 6) return -1;
  return 2 + dowMon0;
}

/** Date → 0=จันทร์ … 6=อาทิตย์ */
function dowMon0_(d) {
  return (d.getDay() + 6) % 7;
}

/** ค่าในแถววันที่ เช่น 10, '8R con*', '9*Interhos*', '18ems' → เลขวัน หรือ null */
function parseDayCell_(v) {
  if (v === null || v === undefined || v === '') return null;
  if (v instanceof Date) return v.getDate();
  if (typeof v === 'number') return Number.isInteger(v) && v >= 1 && v <= 31 ? v : null;
  var m = String(v).trim().match(/^(\d{1,2})(?!\d)/);
  if (!m) return null;
  var n = +m[1];
  return n >= 1 && n <= 31 ? n : null;
}

function isDateRow_(label) {
  return normLabel_(label) === normLabel_(DATE_ROW_LABEL_);
}

/**
 * หา cell ของเวร ใน grid ของเดือน
 * @param {string[]} labels  ค่าคอลัมน์ B ทุกแถว (index = row 0-based)
 * @param {Array<Array>} grid ค่าทุกแถว (index [r][c], c 0-based โดย A=0)
 * @param {number} day  เลขวัน 1–31
 * @param {string} shiftLabel เช่น '8.00 - 16.00'
 * @param {number=} expectDow 0=จันทร์…6=อาทิตย์ (optional cross-check)
 * @return {{r:number,c:number}|{error:string}}
 */
function findShiftInGrid_(labels, grid, day, shiftLabel, expectDow) {
  var want = normLabel_(shiftLabel);
  if (!want) return { error: 'ไม่ได้ระบุเวร' };
  var dateRow = -1, col = -1;
  for (var r = 0; r < labels.length; r++) {
    if (!isDateRow_(labels[r])) continue;
    var row = grid[r] || [];
    for (var c = colIndex_(0); c <= colIndex_(6); c++) {
      if (parseDayCell_(row[c]) === day) { dateRow = r; col = c; break; }
    }
    if (dateRow >= 0) break;
  }
  if (dateRow < 0) return { error: 'ไม่พบวันที่ ' + day + ' ในตารางเดือนนี้' };
  if (expectDow !== undefined && expectDow !== null && colIndex_(expectDow) !== col) {
    return { error: 'วันที่ ' + day + ' อยู่คนละคอลัมน์กับวันในสัปดาห์ที่คาดไว้ (ตรวจปฏิทินของ tab นี้)' };
  }
  for (var rr = dateRow + 1; rr < labels.length; rr++) {
    if (isDateRow_(labels[rr])) break;
    if (normLabel_(labels[rr]) === want) return { r: rr, c: col };
  }
  return { error: 'ไม่พบแถวเวร "' + shiftLabel + '" ในสัปดาห์ของวันที่ ' + day };
}

/** key ระบุเวร 1 block: 'YYYY-MM-DD|normLabel ของแถวในตาราง' (label form กับ label แถว ให้ key เดียวกัน) */
function shiftKey_(date, label) {
  return fmtDate_(date) + '|' + normLabel_(shiftRowLabel_(label) || label);
}

/** ชื่อเดือนทุกแบบสะกดสำหรับ match ชื่อ tab */
function monthNameVariants_(monthIdx) {
  var full = THAI_MONTHS_[monthIdx];
  return [full].concat(THAI_MONTH_ALIASES_[full] || []);
}

/**
 * รายการเวร [{date:Date, shift:string}] ↔ string เก็บใน log:
 *   '2026-09-10|8.00 - 16.00; 2026-09-11|16.00 - 24.00'
 */
function serializeShifts_(list) {
  return (list || []).map(function (x) { return fmtDate_(x.date) + '|' + String(x.shift).trim(); }).join('; ');
}
function parseShifts_(str) {
  if (!str) return [];
  return String(str).split(';').map(function (part) {
    var i = part.indexOf('|');
    if (i < 0) return null;
    var d = parseFormDate_(part.slice(0, i).trim());
    var shift = part.slice(i + 1).trim();
    return d && shift ? { date: d, shift: shift } : null;
  }).filter(Boolean);
}

/** ข้อความสั้นๆ ของรายการเวร สำหรับอีเมล */
function shiftsText_(list) {
  return (list || []).map(function (x) { return fmtDateThai_(x.date) + ' ' + x.shift; }).join(', ');
}

/**
 * อ่าน slot วันที่/เวร จาก namedValues (slot 1..n) → [{date, shift}] หรือ {error}
 * @param {function(number):string[]} dateKeys  key ของวันที่ slot i
 * @param {function(number):string[]} shiftKeys key ของเวร slot i
 */
function readShiftSlots_(named, n, dateKeys, shiftKeys) {
  var out = [], seen = {};
  for (var i = 1; i <= n; i++) {
    var ds = nv_(named, dateKeys(i)), sh = nv_(named, shiftKeys(i));
    if (!ds && !sh) continue;
    if (!ds || !sh) return { error: 'ช่องที่ ' + i + ' ต้องกรอกทั้งวันที่และเวร' };
    var d = parseFormDate_(ds);
    if (!d) return { error: 'ช่องที่ ' + i + ' วันที่ไม่ถูกต้อง: ' + ds };
    var rowLabel = shiftRowLabel_(sh);
    if (!rowLabel) return { error: 'ช่องที่ ' + i + ' เวร "' + sh + '" แลกไม่ได้' };
    var k = shiftKey_(d, rowLabel);
    if (seen[k]) return { error: 'ช่องที่ ' + i + ' ซ้ำกับช่องก่อนหน้า' };
    seen[k] = true;
    out.push({ date: d, shift: shiftDisplayLabel_(rowLabel) });
  }
  return out;
}

/** token สุ่ม (hex) — ใช้ Utilities ถ้ามี ไม่งั้น Math.random (เฉพาะ test) */
function randomToken_(len) {
  len = len || 32;
  var chars = 'abcdefghijklmnopqrstuvwxyz0123456789', out = '';
  for (var i = 0; i < len; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
  return out;
}

/** อ่านค่าจาก namedValues ของ form ด้วย key หลายชื่อ (รองรับหัวข้อไทย/อังกฤษ) */
function nv_(named, keys) {
  for (var i = 0; i < keys.length; i++) {
    var v = named[keys[i]];
    if (v && v.length && String(v[0]).trim() !== '') return String(v[0]).trim();
  }
  // เผื่อ key มี trailing space / ต่างที่ whitespace
  var wanted = keys.map(normLabel_);
  for (var k in named) {
    if (wanted.indexOf(normLabel_(k)) >= 0 && named[k] && named[k].length && String(named[k][0]).trim() !== '') {
      return String(named[k][0]).trim();
    }
  }
  return '';
}

if (typeof module !== 'undefined') {
  module.exports = {
    THAI_MONTHS_: THAI_MONTHS_, SWAPPABLE_SHIFTS_: SWAPPABLE_SHIFTS_, shiftRowLabel_: shiftRowLabel_, shiftDisplayLabel_: shiftDisplayLabel_, monthNameVariants_: monthNameVariants_,
    shiftKey_: shiftKey_, serializeShifts_: serializeShifts_, parseShifts_: parseShifts_, shiftsText_: shiftsText_, readShiftSlots_: readShiftSlots_,
    parseFormDate_: parseFormDate_, fmtDate_: fmtDate_, fmtDateThai_: fmtDateThai_, thaiMonthYear_: thaiMonthYear_,
    normLabel_: normLabel_, baseName_: baseName_, cellHasName_: cellHasName_, replaceName_: replaceName_,
    colIndex_: colIndex_, dowMon0_: dowMon0_, parseDayCell_: parseDayCell_, findShiftInGrid_: findShiftInGrid_,
    randomToken_: randomToken_, nv_: nv_
  };
}
