const { test } = require('node:test');
const assert = require('node:assert/strict');
const { loadGs } = require('./load');
const L = loadGs('lib.gs');
const grid = require('./fixtures/real-september-2569.json').rows;
const labels = grid.map(r => r[1]);
const at = h => grid[h.r][h.c];

test('ตารางจริง ก.ย. 2569: หาเวรได้ถูกช่อง', () => {
  assert.equal(at(L.findShiftInGrid_(labels, grid, 10, '8.00 - 16.00', 3)), 'จุฑามาศ');
  assert.equal(at(L.findShiftInGrid_(labels, grid, 1, 'On floor 1-2', 1)), 'อรรถสิทธิ์');   // สัปดาห์แรกเริ่มอังคาร (col C ว่าง)
  assert.equal(at(L.findShiftInGrid_(labels, grid, 8, '16.00 - 24.00', 1)), 'สุธาพร');       // '8R con*'
  assert.equal(at(L.findShiftInGrid_(labels, grid, 9, '0.00 - 8.00', 2)), 'ภควดี');          // '9*Interhos*'
  assert.equal(at(L.findShiftInGrid_(labels, grid, 18, '8.00 - 16.00', 4)), 'ธนดล');         // '18ems'
  assert.equal(at(L.findShiftInGrid_(labels, grid, 30, '0.00 - 8.00', 2)), 'ภควดี');
  assert.equal(at(L.findShiftInGrid_(labels, grid, 13, 'On floor 1-2', 6)), '');            // เสาร์-อาทิตย์ ไม่มี on floor
});

test('ตารางจริง: วัน 31 ไม่มี → error, dow ผิด → error', () => {
  assert.ok(L.findShiftInGrid_(labels, grid, 31, '8.00 - 16.00').error);
  assert.ok(L.findShiftInGrid_(labels, grid, 10, '8.00 - 16.00', 2).error);
});
