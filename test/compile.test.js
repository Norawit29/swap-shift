// โหลด .gs ทั้งหมดใน vm context เดียว — จับ syntax error และ helper ที่เรียกแต่ไม่มี
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

test('lib.gs + Code.gs + setup.gs parse ได้ และ helper ที่อ้างถึงมีจริง', () => {
  const ctx = { console, Number, Date, Math, String, JSON, Logger: { log() {} } };
  vm.createContext(ctx);
  for (const f of ['lib.gs', 'Code.gs', 'setup.gs']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', f), 'utf8'), ctx, { filename: f });
  }
  // ทุก identifier ที่ลงท้าย _( (helper convention) ต้องถูก define
  const src = ['lib.gs', 'Code.gs', 'setup.gs'].map(f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8')).join('\n');
  const called = new Set([...src.matchAll(/\b([A-Za-z]\w*_)\(/g)].map(m => m[1]));
  const missing = [...called].filter(n => typeof ctx[n] !== 'function');
  assert.deepEqual(missing, [], 'helper ไม่ถูก define: ' + missing.join(', '));
  for (const fn of ['onFormSubmit', 'doGet', 'commitSwap_', 'expirePending', 'setupAll', 'setupForm', 'setupTriggers', 'setWebAppUrl'])
    assert.equal(typeof ctx[fn], 'function', fn);
});
