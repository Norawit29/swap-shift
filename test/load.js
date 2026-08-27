// โหลด lib.gs (Apps Script) เข้า node ผ่าน vm — top-level function declarations กลายเป็น property ของ context
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function loadGs(file) {
  const src = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
  const ctx = { console, Number, Date, Math, String };
  vm.createContext(ctx);
  vm.runInContext(src, ctx, { filename: file });
  return ctx;
}

module.exports = { loadGs };
