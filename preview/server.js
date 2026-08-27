// Local UI preview — โหลด .gs จริงใน vm พร้อม stub Apps Script globals แล้ว render อีเมล/หน้า web app/mock Form
const http = require('http');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PORT = process.env.PORT || 3456;
const ctx = {
  console, Number, Date, Math, String, JSON, encodeURIComponent,
  Logger: { log: (...a) => console.log('[Logger]', ...a) },
  PropertiesService: { getScriptProperties: () => ({ getProperty: k => ({ WEB_APP_URL: 'http://localhost:3456/exec', PENDING_DAYS: '3' })[k] || null, getProperties: () => ({}) }) },
  HtmlService: { createHtmlOutput: html => ({ html, setTitle() { return this; } }) },
  Utilities: { getUuid: () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx' },
};
vm.createContext(ctx);
for (const f of ['lib.gs', 'Code.gs', 'setup.gs']) vm.runInContext(fs.readFileSync(path.join(__dirname, '..', f), 'utf8'), ctx, { filename: f });

const row = {
  swap_id: 'SW20260827-0001', status: 'pending_b', type: 'swap',
  a_name: 'norawit29', a_email: 'norawit29@gmail.com', a_shifts: '2026-09-10|8.00 - 16.00 (1); 2026-09-11|16.00 - 24.00',
  b_name: 'norawit.kij', b_email: 'norawit.kij29@gmail.com', b_shifts: '2026-09-12|0.00 - 8.00; 2026-09-14|8.00 - 16.00 (2)',
  note: 'ติดประชุมวันที่ 10 ครับ', sheets: 'กันยายน2569 (แลก5)', token_b: 'tok'
};
const giveRow = { ...row, swap_id: 'SW20260827-0002', type: 'give', b_shifts: '', note: '' };

const NAV = [['/', 'Index'], ['/app', 'Web app'], ['/login', 'Login'], ['/form', 'Form'], ['/email/b', 'Email → B'], ['/email/a', 'Email → A'], ['/email/give', 'Email ฝากเวร'], ['/email/committed', 'Email สำเร็จ'], ['/email/error', 'Email error'], ['/email/expired', 'Email หมดอายุ'],
  ['/exec?a=approve', 'Page สำเร็จ'], ['/exec?a=reject', 'Page ปฏิเสธ'], ['/exec?a=done', 'Page ซ้ำ'], ['/exec?a=fail', 'Page error']];

const wrap = (title, inner, extraCss = '') => `<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;700&display=swap" rel="stylesheet">
<style>*{box-sizing:border-box}body{font-family:Sarabun,-apple-system,"Segoe UI",sans-serif;background:#eef2f6;margin:0;color:#1e293b}
nav{background:#0f172a;padding:10px 16px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;position:sticky;top:0;z-index:9}
nav .logo{color:#5eead4;font-weight:700;margin-right:10px;font-size:14px}nav a{color:#cbd5e1;text-decoration:none;font-size:12px;padding:5px 10px;border-radius:999px;background:#1e293b}nav a:hover{background:#334155;color:#fff}
.client{max-width:680px;margin:28px auto;background:#fff;border-radius:14px;box-shadow:0 10px 30px rgba(15,23,42,.08);border:1px solid #e2e8f0;overflow:hidden}
.hdr{padding:18px 22px;border-bottom:1px solid #eef2f6;display:flex;gap:14px;align-items:flex-start}.av{width:42px;height:42px;border-radius:50%;background:#0f766e;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none}
.hdr .subj{font-size:17px;font-weight:700;color:#0f172a;margin:0 0 4px;line-height:1.35}.hdr .meta{font-size:12.5px;color:#64748b;line-height:1.5}.hdr .meta b{color:#334155;font-weight:500}
.mailbody{padding:8px 22px 4px;font-size:15px;line-height:1.65;color:#334155}.mailbody>p{margin:12px 0}.mailbody>p b{color:#0f172a}.mailbody a{color:#0f766e}
.mailfoot{padding:18px 22px 26px;margin-top:16px;border-top:1px solid #e3e8ee;font-size:12px;color:#8a97a8;text-align:center}.mailfoot span{color:#0f766e;font-weight:700}
${extraCss}</style></head><body><nav><span class="logo">ER แลกเวร · preview</span>${NAV.map(([h, l]) => `<a href="${h}">${l}</a>`).join('')}</nav>${inner}</body></html>`;

const mail = (to, subject, body) => wrap(subject, `<div class="client"><div class="hdr"><div class="av">ER</div><div><p class="subj">${subject}</p><div class="meta"><b>ER แลกเวร</b> &lt;no-reply&gt;<br>to <b>${to}</b> · ${new Date().toLocaleDateString('th-TH', { day: 'numeric', month: 'short' })}</div></div></div>
<div class="mailbody">${body}</div><div class="mailfoot"><span>ER แลกเวร</span> · อีเมลอัตโนมัติ กรุณาอย่าตอบกลับ</div></div>`);

const approve = ctx.link_('http://localhost:3456/exec', row.swap_id, 'tok', 'approve', 'b');
const reject = ctx.link_('http://localhost:3456/exec', row.swap_id, 'tok', 'reject', 'b');

function formHtml() {
  const Q = ctx.Q, names = ['norawit29', 'norawit.kij'], shifts = ctx.SWAPPABLE_SHIFTS_;
  const lbl = (t, req) => `<label>${t}${req ? ' <span class="req">*</span>' : ''}</label>`;
  const opts = (list, ph) => `<option value="">${ph}</option>${list.map(o => `<option>${o}</option>`).join('')}`;
  const sel = (title, list, req) => `<div class="card"><div class="q">${lbl(title, req)}<select>${opts(list, 'เลือก')}</select></div></div>`;
  const slot = (dateT, shiftT, req) => `<div class="card"><div class="slot"><div class="q">${lbl(dateT, req)}<input type="date"></div><div class="q">${lbl(shiftT, req)}<select>${opts(shifts, 'เลือกเวร')}</select></div></div></div>`;
  const section = (h, p, cls) => `<div class="sec ${cls}"><h3>${h}</h3><p>${p}</p></div>`;
  let h = sel(Q.A_NAME, names, true) + sel(Q.B_NAME, names, true);
  h += section('เวรของคุณ (ที่จะยกให้อีกฝ่าย)', 'กรอกอย่างน้อย 1 เวร — เวรละ 1 block 8 ชั่วโมง แลกข้ามเช้า/บ่าย/ดึกได้', 'mine');
  for (let i = 1; i <= ctx.MAX_SLOTS; i++) h += slot(Q.A_DATE(i), Q.A_SHIFT(i), i === 1);
  h += section('เวรของอีกฝ่าย (ที่คุณจะรับมา)', 'เว้นว่างทั้งหมด = ฝากเวร (ยกเวรของคุณให้อีกฝ่ายโดยไม่รับเวรกลับ)', 'theirs');
  for (let j = 1; j <= ctx.MAX_SLOTS; j++) h += slot(Q.B_DATE(j), Q.B_SHIFT(j), false);
  h += `<div class="card"><div class="q">${lbl(Q.NOTE)}<textarea rows="3" placeholder="คำตอบของคุณ"></textarea></div></div><div class="actions"><button>ส่ง</button><a href="#" class="clear">ล้างแบบฟอร์ม</a></div>`;
  const css = `.gf{max-width:640px;margin:20px auto;padding:0 12px}.card{background:#fff;border:1px solid #dadce0;border-radius:8px;padding:22px 24px;margin:12px 0}
.head{border-top:10px solid #0f766e;padding:26px 24px 22px}.head h2{margin:0 0 10px;font-size:30px;font-weight:400;color:#202124}.head p{margin:0;color:#5f6368;font-size:14px;line-height:1.6}
.mailrow{font-size:14px;color:#202124;margin-top:16px;padding-top:14px;border-top:1px solid #dadce0}.mailrow i{color:#5f6368}.reqnote{color:#d93025;font-size:14px;margin-top:8px}
.q{margin:0}label{display:block;font-size:15px;font-weight:500;color:#202124;margin-bottom:10px}.req{color:#d93025}
select,input,textarea{width:100%;padding:10px 12px;font-size:14px;font-family:inherit;border:1px solid #dadce0;border-radius:6px;background:#fff;color:#202124}select:focus,input:focus,textarea:focus{outline:2px solid #0f766e;border-color:transparent}
.slot{display:grid;grid-template-columns:1fr 1fr;gap:16px 20px}@media (max-width:520px){.slot{grid-template-columns:1fr}}
.sec{border-radius:8px;padding:16px 24px;margin:18px 0 8px;border-left:6px solid}.sec.mine{background:#e6f5f3;border-color:#0f766e}.sec.theirs{background:#eef2ff;border-color:#4f46e5}.sec h3{margin:0 0 4px;font-size:17px;font-weight:600;color:#0f172a}.sec p{margin:0;color:#475569;font-size:13px}
.actions{display:flex;justify-content:space-between;align-items:center;margin:18px 0 40px}button{background:#0f766e;color:#fff;border:0;padding:10px 26px;border-radius:6px;font-size:14px;font-family:inherit;font-weight:500;cursor:pointer}.clear{font-size:14px;color:#0f766e;text-decoration:none}
.foot{text-align:center;color:#5f6368;font-size:12px;margin-bottom:30px}`;
  return wrap('Form mock', `<div class="gf"><div class="card head"><h2>ER แลกเวร</h2><p style="white-space:pre-line">ยื่นคำขอแลก/ฝากเวร attending ER — ระบบจะตรวจว่าเป็นเจ้าของเวรจริง แล้วส่งอีเมลให้อีกฝ่ายกดตกลง ครบแล้วจึงแก้ตารางเวรให้อัตโนมัติ
แลกได้หลายเวรในคำขอเดียว (สูงสุด ${ctx.MAX_SLOTS} เวรต่อฝั่ง) — อีกฝ่ายจะตกลง/ปฏิเสธทั้งชุดในครั้งเดียว</p>
<div class="mailrow">norawit29@gmail.com <i>(verified — Google Form จะแสดงเอง)</i></div><div class="reqnote">* ต้องตอบคำถามนี้</div></div>${h}<div class="foot">แบบฟอร์มนี้เป็น mock สำหรับ preview — ของจริงคือ Google Form</div></div>`, css);
}


// ───── web app (app.html) with mock API ─────
const FIX = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'test', 'fixtures', 'real-september-2569.json'), 'utf8')).rows;
const ME = 'ธนดล';
function mockSchedule(ym) {
  // same classification rules as apiSchedule in app.gs, using the real helpers from lib.gs
  const m = ym.match(/^(\d{4})-(\d{2})$/); const first = new Date(+m[1], +m[2] - 1, 1);
  const rows = []; let curDays = null, started = false;
  for (let r = 0; r < FIX.length; r++) {
    const label = String(FIX[r][1] || ''); let kind;
    if (r === 0) kind = 'title'; else if (r === 1) kind = 'dow';
    else if (ctx.isDateRow_(label)) { kind = 'date'; started = true; }
    else if (ctx.shiftRowLabel_(label)) kind = 'shift';
    else if (ctx.normLabel_(label).indexOf('conference') === 0) kind = 'conf';
    else if (started) break; else kind = 'other';
    if (kind === 'date') curDays = [];
    const cells = [];
    for (let c = ctx.colIndex_(0); c <= ctx.colIndex_(6); c++) {
      const v = String(FIX[r][c] || ''); const cell = { v };
      if (kind === 'date') { const day = ctx.parseDayCell_(v); curDays[c] = day; cell.day = day; if (day) cell.date = ctx.fmtDate_(new Date(first.getFullYear(), first.getMonth(), day)); }
      else if (kind === 'shift' && curDays && curDays[c]) { cell.date = ctx.fmtDate_(new Date(first.getFullYear(), first.getMonth(), curDays[c])); cell.owner = ctx.baseName_(v) || ''; cell.swappable = !!cell.owner; cell.mine = ctx.cellHasName_(v, ME); }
      cells.push(cell);
    }
    rows.push({ kind, label, shift: kind === 'shift' ? ctx.shiftDisplayLabel_(label) : null, cells });
  }
  return { ym, sheetName: 'กันยายน2569 (แลก5)', title: String(FIX[0][1] || ''), rows, me: ME };
}
const MONTHS = [{ ym: '2026-08', label: 'สิงหาคม 2569', sheetName: 'สิงหาคม2569' }, { ym: '2026-09', label: 'กันยายน 2569', sheetName: 'กันยายน2569 (แลก5)' }];
const th = d => ctx.fmtDateThai_(ctx.parseFormDate_(d));
const sh = (d, s) => ({ date: d, dateThai: th(d), shift: s });
const HISTORY = [
  { swap_id: 'SW20260827-0003', created_at: '27 ส.ค. 69 09:12', updated_at: '27 ส.ค. 69 09:12', status: 'pending_b', statusThai: 'รออีกฝ่ายตอบรับ', type: 'swap', a_name: 'คมสันติ', b_name: ME, a_shifts: [sh('2026-09-07', '8.00 - 16.00 (1)')], b_shifts: [sh('2026-09-11', '8.00 - 16.00 (1)')], note: 'ขอแลกวันที่ 7 ครับ ติดสอน', message: '', mine: 'b' },
  { swap_id: 'SW20260820-0002', created_at: '20 ส.ค. 69 14:30', updated_at: '21 ส.ค. 69 08:05', status: 'committed', statusThai: 'แลกเวรสำเร็จ', type: 'swap', a_name: ME, b_name: 'ภควดี', a_shifts: [sh('2026-09-03', '8.00 - 16.00 (1)'), sh('2026-09-06', '16.00 - 24.00')], b_shifts: [sh('2026-09-12', '16.00 - 24.00')], note: '', message: 'เขียนตารางแล้ว 4 ช่อง', mine: 'a' },
  { swap_id: 'SW20260815-0001', created_at: '15 ส.ค. 69 22:41', updated_at: '15 ส.ค. 69 22:41', status: 'error', statusThai: 'ผิดพลาด', type: 'give', a_name: ME, b_name: 'สุธาพร', a_shifts: [sh('2026-09-16', '0.00 - 8.00')], b_shifts: [], note: 'ฝากเวรดึกครับ', message: 'เวรของคุณ พ. 16 กันยายน 2569 0.00 - 8.00 ในตารางตอนนี้เป็นของ "ขวัญศิริ" ไม่ใช่ ธนดล', mine: 'a' },
];
const wait = (ms, v) => new Promise(r => setTimeout(() => r(v), ms));
const MOCK = `<script>
var wait = ${wait.toString()};
window.MOCK_API = {
  apiRequestLogin: function (email) { return wait(500, { ok: true, message: 'ส่งลิงก์แล้ว (mock) ไปที่ ' + email }); },
  apiMe: function (s) { return wait(250, { email: 'thanadol@example.com', name: ${JSON.stringify(ME)}, role: 'staff', months: ${JSON.stringify(MONTHS)}, currentYm: '2026-09', shifts: ${JSON.stringify(ctx.SWAPPABLE_SHIFTS_)}, roster: ['ธนดล','คมสันติ','ภควดี','สุธาพร'], maxSlots: 10 }); },
  apiSchedule: function (s, ym) { return wait(400, JSON.parse(JSON.stringify(window.__SCHED[ym] || window.__SCHED['2026-09']))); },
  apiMyShifts: function (s, ym) { var g = window.__SCHED[ym] || window.__SCHED['2026-09'], out = []; g.rows.forEach(function (r) { if (r.kind !== 'shift') return; r.cells.forEach(function (c, i) { if (c.mine) out.push({ date: c.date, shift: r.shift, dow: i }); }); }); return { ym: ym, shifts: out }; },
  apiHistory: function (s) { return wait(300, { history: ${JSON.stringify(HISTORY)} }); },
  apiSubmit: function (s, p) { console.log('apiSubmit', p); return wait(600, { ok: true, swap_id: 'SW20260827-0009', b_email: 'x@example.com' }); },
  apiLogout: function () { return { ok: true }; }
};
window.__SCHED = { '2026-09': ${JSON.stringify(mockSchedule('2026-09'))}, '2026-08': ${JSON.stringify(mockSchedule('2026-08'))} };
</script>`;
function appHtml(session) {
  return fs.readFileSync(path.join(__dirname, '..', 'app.html'), 'utf8')
    .replace('<?= session ?>', session).replace('<?= loginError ?>', '').replace('<?= appUrl ?>', `http://localhost:${PORT}/app`)
    .replace('<!--MOCK-->', MOCK);
}

const routes = {
  '/app': (q) => appHtml(q.get('logged_out') ? '' : 'mock-session'),
  '/login': () => appHtml(''),
  '/': () => wrap('index', `<div class="client"><div class="hdr"><div class="av">ER</div><div><p class="subj">ER แลกเวร — UI preview</p><div class="meta">ทุกหน้า render จากโค้ดจริงใน Code.gs (summaryHtml_, buttonsHtml_, page_) — ยกเว้น Form ที่เป็น mock ตาม buildQuestions_ (ของจริงคือ Google Form)</div></div></div>
<div class="mailbody"><ol style="padding-left:20px;line-height:2;margin:8px 0 20px">
<li><a href="/app"><b>Web app (SPA, mock API)</b></a> / <a href="/login">หน้า login</a></li><li><a href="/form">Form (mock)</a></li><li><a href="/email/a">อีเมลยืนยันถึง A</a></li><li><a href="/email/b">อีเมลถึง B (มีปุ่ม)</a></li><li><a href="/email/give">อีเมลฝากเวร</a></li>
<li><a href="/exec?a=approve">หน้า web app: สำเร็จ</a> / <a href="/exec?a=reject">ปฏิเสธ</a> / <a href="/exec?a=done">กดซ้ำ</a> / <a href="/exec?a=fail">error</a></li>
<li><a href="/email/committed">อีเมลสำเร็จ</a> / <a href="/email/error">อีเมล error</a> / <a href="/email/expired">อีเมลหมดอายุ</a></li></ol></div></div>`),
  '/form': formHtml,
  '/email/b': () => mail(row.b_email, `[ER แลกเวร] ${row.a_name} ขอแลกเวรกับคุณ (${row.swap_id})`,
    `<p>${row.a_name} ส่งคำขอแลกเวรถึงคุณ กรุณาตรวจสอบแล้วกดตกลง/ปฏิเสธ <b>ครั้งเดียวสำหรับทุกเวรในคำขอนี้</b></p>` + ctx.summaryHtml_(row) + ctx.buttonsHtml_(approve, reject) +
    `<p style="color:#666">ลิงก์ใช้ได้ครั้งเดียว และหมดอายุใน 3 วัน — ถ้าไม่ตอบ คำขอจะถูกยกเลิกอัตโนมัติ</p>`),
  '/email/a': () => mail(row.a_email, `[ER แลกเวร] ส่งคำขอ ${row.swap_id} ให้ ${row.b_name} แล้ว`, `<p>ระบบส่งคำขอของคุณให้ ${row.b_name} แล้ว รอการตอบรับ</p>` + ctx.summaryHtml_(row)),
  '/email/give': () => mail(giveRow.b_email, `[ER แลกเวร] ${giveRow.a_name} ขอฝากเวรกับคุณ (${giveRow.swap_id})`, `<p>${giveRow.a_name} ส่งคำขอฝากเวรถึงคุณ</p>` + ctx.summaryHtml_(giveRow) + ctx.buttonsHtml_(approve, reject)),
  '/email/committed': () => mail(`${row.a_email}, ${row.b_email}`, `[ER แลกเวร] ${row.swap_id} สำเร็จ — ตารางเวรถูกแก้แล้ว`, `<p>ระบบแก้ตารางเวรตามคำขอนี้เรียบร้อยแล้ว (4 ช่อง, tab ${row.sheets})</p>` + ctx.summaryHtml_(row)),
  '/email/error': () => mail(row.a_email, `[ER แลกเวร] คำขอ ${row.swap_id} ไม่ผ่านการตรวจสอบ`, `<p>คำขอของคุณไม่ผ่านการตรวจสอบ:</p><p><b>เวรของคุณ พฤ. 10 กันยายน 2569 8.00 - 16.00 ในตารางตอนนี้เป็นของ "จุฑามาศ" ไม่ใช่ norawit29</b></p>` + ctx.summaryHtml_(row) + `<p>กรุณาตรวจสอบตารางเวรแล้วส่ง Form ใหม่</p>`),
  '/email/expired': () => mail(`${row.a_email}, ${row.b_email}`, `[ER แลกเวร] คำขอ ${row.swap_id} หมดอายุ`, `<p>คำขอนี้ไม่ได้รับการตอบรับภายใน 3 วัน ระบบยกเลิกให้แล้ว ตารางเวรไม่ถูกแก้</p>` + ctx.summaryHtml_(row)),
  '/exec': (q) => {
    const a = q.get('a');
    const pages = {
      approve: ctx.page_('แลกเวรสำเร็จ', `เขียนคำขอ ${row.swap_id} ลงตารางเวรแล้ว (4 ช่อง) ระบบแจ้งทั้งสองฝ่ายทางอีเมล`),
      reject: ctx.page_('ปฏิเสธคำขอแล้ว', `บันทึกการปฏิเสธคำขอ ${row.swap_id} แล้ว ระบบแจ้ง ${row.a_name} ทางอีเมล`),
      done: ctx.page_('คำขอนี้ถูกดำเนินการแล้ว', `คำขอ ${row.swap_id} อยู่ในสถานะ <b>แลกเวรสำเร็จ</b> แล้ว ไม่สามารถทำซ้ำได้`),
      fail: ctx.page_('เขียนตารางไม่สำเร็จ', `เวรของ norawit29 พฤ. 11 กันยายน 2569 16.00 - 24.00 ในตารางตอนนี้เป็นของ "ธนดล" ไม่ใช่ norawit29 (ตารางถูกแก้ระหว่างรอ?)<br>ระบบแจ้งทุกฝ่ายทางอีเมลแล้ว`),
    };
    return (pages[a] || pages.approve).html;
  },
};

http.createServer((req, res) => {
  const u = new URL(req.url, 'http://localhost');
  const h = routes[u.pathname];
  res.writeHead(h ? 200 : 404, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(h ? h(u.searchParams) : 'not found');
}).listen(PORT, () => console.log(`UI preview: http://localhost:${PORT}`));
