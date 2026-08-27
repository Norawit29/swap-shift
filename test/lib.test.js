const { test } = require('node:test');
const assert = require('node:assert/strict');
// object จาก vm context มี Object.prototype คนละตัว → เทียบผ่าน JSON
const deepEqual = assert.deepEqual;
assert.deepEqual = (a, b, msg) => deepEqual(JSON.parse(JSON.stringify(a)), JSON.parse(JSON.stringify(b)), msg);
const { loadGs } = require('./load');

const L = loadGs('lib.gs');
const fx = require('./fixtures/september-2569.json');
const grid = fx.rows;
const labels = grid.map(r => r[1]);

test('findShiftInGrid_: day 10 / 8.00 - 16.00 → cell ถูกต้อง', () => {
  const hit = L.findShiftInGrid_(labels, grid, 10, '8.00 - 16.00');
  assert.deepEqual(hit, { r: 3, c: 5 });
  assert.equal(grid[hit.r][hit.c], 'สุรีย์ภรณ์');
});

test('findShiftInGrid_: day 8 จาก "8R con*" parse เลขวันได้', () => {
  const hit = L.findShiftInGrid_(labels, grid, 8, '16.00 - 24.00');
  assert.deepEqual(hit, { r: 7, c: 3 });
  assert.equal(grid[hit.r][hit.c], 'กิตติ');
});

test('findShiftInGrid_: day 9 จาก "9*Interhos*" และ day 18 จาก "18ems"', () => {
  assert.deepEqual(L.findShiftInGrid_(labels, grid, 9, '0.00 - 8.00'), { r: 8, c: 4 });
  assert.deepEqual(L.findShiftInGrid_(labels, grid, 18, '8.00 - 16.00'), { r: 10, c: 6 });
});

test('findShiftInGrid_: label "On floor 1-2" เทียบแบบ ignore whitespace/case (fixture มี trailing space)', () => {
  assert.deepEqual(L.findShiftInGrid_(labels, grid, 14, 'on floor1-2'), { r: 11, c: 2 });
  assert.deepEqual(L.findShiftInGrid_(labels, grid, 8, 'ON FLOOR 1-2'), { r: 4, c: 3 });
  assert.deepEqual(L.findShiftInGrid_(labels, grid, 8, 'conference 3-4, TM'), { r: 6, c: 3 });
});

test('findShiftInGrid_: ช่องว่าง = ไม่มีเวร (หา cell เจอแต่ค่าว่าง)', () => {
  const hit = L.findShiftInGrid_(labels, grid, 12, '8.00 - 16.00');
  assert.deepEqual(hit, { r: 3, c: 7 });
  assert.equal(grid[hit.r][hit.c], '');
  assert.equal(L.cellHasName_(grid[hit.r][hit.c], 'ธนดล'), false);
});

test('findShiftInGrid_: วันไม่มีในตาราง → error', () => {
  const res = L.findShiftInGrid_(labels, grid, 25, '8.00 - 16.00');
  assert.ok(res.error);
  assert.match(res.error, /25/);
});

test('findShiftInGrid_: เวรไม่มีใน block → error', () => {
  const res = L.findShiftInGrid_(labels, grid, 10, 'night 99');
  assert.ok(res.error);
});

test('findShiftInGrid_: cross-check วันในสัปดาห์', () => {
  // 10 ก.ย. 2569 = พฤหัส = dow 3 → col 5
  assert.deepEqual(L.findShiftInGrid_(labels, grid, 10, '8.00 - 16.00', 3), { r: 3, c: 5 });
  assert.ok(L.findShiftInGrid_(labels, grid, 10, '8.00 - 16.00', 0).error);
});

test('parseDayCell_ หลายรูปแบบ', () => {
  assert.equal(L.parseDayCell_(10), 10);
  assert.equal(L.parseDayCell_('10'), 10);
  assert.equal(L.parseDayCell_('8R con*'), 8);
  assert.equal(L.parseDayCell_('9*Interhos*'), 9);
  assert.equal(L.parseDayCell_('18ems'), 18);
  assert.equal(L.parseDayCell_(''), null);
  assert.equal(L.parseDayCell_('ems'), null);
  assert.equal(L.parseDayCell_('100'), null);
});

test('cellHasName_ ignore suffix TM', () => {
  assert.equal(L.cellHasName_('สุรีย์ภรณ์ TM', 'สุรีย์ภรณ์'), true);
  assert.equal(L.cellHasName_('สุรีย์ภรณ์', 'สุรีย์ภรณ์'), true);
  assert.equal(L.cellHasName_(' สุรีย์ภรณ์  TM ', 'สุรีย์ภรณ์'), true);
  assert.equal(L.cellHasName_('สุรีย์ภรณ์ TM', 'ธนดล'), false);
  assert.equal(L.cellHasName_('', 'ธนดล'), false);
  assert.equal(L.cellHasName_('ธนดล2', 'ธนดล'), false);
});

test('replaceName_ รักษา suffix TM', () => {
  assert.equal(L.replaceName_('สุรีย์ภรณ์ TM', 'สุรีย์ภรณ์', 'ธนดล'), 'ธนดล TM');
  assert.equal(L.replaceName_('สุรีย์ภรณ์', 'สุรีย์ภรณ์', 'ธนดล'), 'ธนดล');
  assert.equal(L.replaceName_('กิตติ', 'สุรีย์ภรณ์', 'ธนดล'), 'กิตติ', 'ไม่ใช่เจ้าของ → คงเดิม');
});

test('parseFormDate_ รับ 2026-09-10, 10/09/2026, Date, พ.ศ.', () => {
  assert.equal(L.fmtDate_(L.parseFormDate_('2026-09-10')), '2026-09-10');
  assert.equal(L.fmtDate_(L.parseFormDate_('10/09/2026')), '2026-09-10');
  assert.equal(L.fmtDate_(L.parseFormDate_('10/9/2026')), '2026-09-10');
  assert.equal(L.fmtDate_(L.parseFormDate_('10/09/2569')), '2026-09-10');
  assert.equal(L.fmtDate_(L.parseFormDate_('2026-09-10 00:00:00')), '2026-09-10');
  assert.equal(L.fmtDate_(L.parseFormDate_(new Date(2026, 8, 10, 15, 30))), '2026-09-10');
  assert.equal(L.parseFormDate_('31/02/2026'), null);
  assert.equal(L.parseFormDate_('abc'), null);
  assert.equal(L.parseFormDate_(''), null);
});

test('fmtDateThai_ / thaiMonthYear_', () => {
  const d = L.parseFormDate_('2026-09-10');
  assert.equal(L.fmtDateThai_(d), 'พฤ. 10 กันยายน 2569');
  assert.deepEqual(L.thaiMonthYear_(d), { month: 'กันยายน', yearBE: 2569 });
});

test('normLabel_ / colIndex_ / dowMon0_', () => {
  assert.equal(L.normLabel_(' On Floor 1-2 '), 'onfloor1-2');
  assert.equal(L.normLabel_('conference 3-4,TM'), 'conference3-4,tm');
  assert.equal(L.colIndex_(0), 2); // จันทร์ = C
  assert.equal(L.colIndex_(6), 8); // อาทิตย์ = I
  assert.equal(L.colIndex_(7), -1);
  assert.equal(L.dowMon0_(new Date(2026, 8, 7)), 0); // 7 ก.ย. 2569 จันทร์
  assert.equal(L.dowMon0_(new Date(2026, 8, 13)), 6);
});

test('nv_ อ่าน namedValues ด้วย key ไทย/อังกฤษ และ trailing space', () => {
  const named = { 'ที่อยู่อีเมล': ['a@x.com'], 'วันที่เวรของคุณ ': ['2026-09-10'] };
  assert.equal(L.nv_(named, ['Email Address', 'ที่อยู่อีเมล']), 'a@x.com');
  assert.equal(L.nv_(named, ['วันที่เวรของคุณ']), '2026-09-10');
  assert.equal(L.nv_(named, ['ไม่มี']), '');
});

test('parseDayCell_ รับค่าจากไฟล์จริง: "1.0", "5 วันพระบรมราช", "15R con*"', () => {
  assert.equal(L.parseDayCell_('1.0'), 1);
  assert.equal(L.parseDayCell_('5 วันพระบรมราช'), 5);
  assert.equal(L.parseDayCell_('15R con*'), 15);
  assert.equal(L.parseDayCell_(1.0), 1);
});

test('serializeShifts_ ↔ parseShifts_ round-trip, shiftKey_', () => {
  const list = [{ date: L.parseFormDate_('2026-09-10'), shift: '8.00 - 16.00' }, { date: L.parseFormDate_('2026-09-11'), shift: '16.00 - 24.00' }];
  const s = L.serializeShifts_(list);
  assert.equal(s, '2026-09-10|8.00 - 16.00; 2026-09-11|16.00 - 24.00');
  const back = L.parseShifts_(s);
  assert.equal(back.length, 2);
  assert.equal(L.fmtDate_(back[1].date), '2026-09-11');
  assert.equal(back[1].shift, '16.00 - 24.00');
  assert.equal(L.parseShifts_('').length, 0);
  assert.equal(L.shiftKey_(list[0].date, ' 8.00 - 16.00 '), '2026-09-10|8.00-16.00');
});

test('readShiftSlots_: หลาย slot, ข้ามช่องว่าง, ปฏิเสธ conference/ซ้ำ/กรอกครึ่งเดียว', () => {
  const dk = i => ['วันที่ #' + i], sk = i => ['เวร #' + i];
  const ok = L.readShiftSlots_({ 'วันที่ #1': ['2026-09-10'], 'เวร #1': ['8.00 - 16.00'], 'วันที่ #2': [''], 'เวร #2': [''], 'วันที่ #3': ['2026-09-12'], 'เวร #3': ['0.00 - 8.00'] }, 4, dk, sk);
  assert.equal(ok.length, 2);
  assert.equal(ok[1].shift, '0.00 - 8.00');
  assert.ok(L.readShiftSlots_({ 'วันที่ #1': ['2026-09-10'], 'เวร #1': ['conference 3-4'] }, 4, dk, sk).error);
  // label (1)/(2) → เก็บเป็น label แสดงผล และ key ตรงกับแถวในตาราง
  const morn = L.readShiftSlots_({ 'วันที่ #1': ['2026-09-10'], 'เวร #1': ['8.00 - 16.00 (2)'], 'วันที่ #2': ['2026-09-10'], 'เวร #2': ['On floor 1-2'] }, 4, dk, sk);
  assert.ok(morn.error, '(2) กับ On floor 1-2 คือช่องเดียวกัน → ซ้ำ');
  assert.equal(L.readShiftSlots_({ 'วันที่ #1': ['2026-09-10'], 'เวร #1': ['On floor 1-2'] }, 4, dk, sk)[0].shift, '8.00 - 16.00 (2)');
  assert.ok(L.readShiftSlots_({ 'วันที่ #1': ['2026-09-10'], 'เวร #1': [''] }, 4, dk, sk).error);
  assert.ok(L.readShiftSlots_({ 'วันที่ #1': ['2026-09-10'], 'เวร #1': ['8.00 - 16.00'], 'วันที่ #2': ['10/09/2026'], 'เวร #2': ['8.00-16.00'] }, 4, dk, sk).error, 'ซ้ำ');
  assert.equal(L.readShiftSlots_({}, 4, dk, sk).length, 0);
});

test('shiftRowLabel_ / shiftDisplayLabel_: เวรเช้า (1)/(2) ↔ แถวในตาราง', () => {
  assert.equal(L.shiftRowLabel_('8.00 - 16.00 (1)'), '8.00 - 16.00');
  assert.equal(L.shiftRowLabel_('8.00-16.00 (2)'), 'On floor 1-2');
  assert.equal(L.shiftRowLabel_('16.00 - 24.00'), '16.00 - 24.00');
  assert.equal(L.shiftRowLabel_('conference 3-4'), null);
  assert.equal(L.shiftDisplayLabel_('On floor 1-2'), '8.00 - 16.00 (2)');
  assert.equal(L.shiftDisplayLabel_('0.00 - 8.00'), '0.00 - 8.00');
  assert.equal(L.shiftKey_(L.parseFormDate_('2026-09-10'), '8.00 - 16.00 (2)'), '2026-09-10|onfloor1-2');
});

test('monthNameVariants_ รองรับ กรกฏาคม (ฏ) ที่ใช้ใน tab จริง', () => {
  assert.deepEqual(L.monthNameVariants_(6), ['กรกฎาคม', 'กรกฏาคม']);
  assert.deepEqual(L.monthNameVariants_(8), ['กันยายน']);
});
