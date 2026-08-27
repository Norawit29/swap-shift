// Local UI preview — โหลด .gs จริงใน vm พร้อม stub Apps Script globals แล้ว render อีเมล/หน้า web app/mock Form
const http = require('http');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

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
  a_name: 'norawit29', a_email: 'norawit29@gmail.com', a_shifts: '2026-09-10|8.00 - 16.00; 2026-09-11|16.00 - 24.00',
  b_name: 'norawit.kij', b_email: 'norawit.kij29@gmail.com', b_shifts: '2026-09-12|0.00 - 8.00; 2026-09-14|On floor 1-2',
  note: 'ติดประชุมวันที่ 10 ครับ', sheets: 'กันยายน2569 (แลก5)', token_b: 'tok'
};
const giveRow = { ...row, swap_id: 'SW20260827-0002', type: 'give', b_shifts: '', note: '' };

const wrap = (title, inner) => `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>
<style>body{font-family:-apple-system,sans-serif;background:#eee;margin:0}nav{background:#222;color:#fff;padding:10px 16px}nav a{color:#9cf;margin-right:14px}
.mail{max-width:640px;margin:24px auto;background:#fff;padding:24px;border-radius:8px;box-shadow:0 1px 4px #0002}.hdr{color:#666;font-size:13px;border-bottom:1px solid #ddd;padding-bottom:8px;margin-bottom:16px}</style></head>
<body><nav><a href="/">index</a><a href="/form">Form</a><a href="/email/b">email→B</a><a href="/email/a">email→A</a><a href="/email/give">email ฝากเวร</a><a href="/email/committed">email สำเร็จ</a><a href="/email/error">email error</a><a href="/exec?a=approve">page สำเร็จ</a><a href="/exec?a=reject">page ปฏิเสธ</a><a href="/exec?a=done">page ซ้ำ</a><a href="/exec?a=fail">page error</a></nav>${inner}</body></html>`;

const mail = (to, subject, body) => wrap(subject, `<div class="mail"><div class="hdr"><b>To:</b> ${to}<br><b>From:</b> ER แลกเวร<br><b>Subject:</b> ${subject}</div>${body}<hr><p style="color:#999;font-size:12px">ER แลกเวร — อีเมลอัตโนมัติ กรุณาอย่าตอบกลับ</p></div>`);

const approve = ctx.link_('http://localhost:3456/exec', row.swap_id, 'tok', 'approve', 'b');
const reject = ctx.link_('http://localhost:3456/exec', row.swap_id, 'tok', 'reject', 'b');

function formHtml() {
  const Q = ctx.Q, names = ['norawit29', 'norawit.kij'], shifts = ctx.SWAPPABLE_SHIFTS_;
  const sel = (title, opts, req) => `<div class="q"><label>${title}${req ? ' <span class="req">*</span>' : ''}</label><select><option value="">เลือก</option>${opts.map(o => `<option>${o}</option>`).join('')}</select></div>`;
  const date = (title, req) => `<div class="q"><label>${title}${req ? ' <span class="req">*</span>' : ''}</label><input type="date"></div>`;
  let h = '';
  h += sel(Q.A_NAME, names, true) + sel(Q.B_NAME, names, true);
  h += `<div class="sec"><h3>เวรของคุณ (ที่จะยกให้อีกฝ่าย)</h3><p>กรอกอย่างน้อย 1 เวร — เวรละ 1 block 8 ชั่วโมง แลกข้ามเช้า/บ่าย/ดึกได้</p></div>`;
  for (let i = 1; i <= ctx.MAX_SLOTS; i++) h += date(Q.A_DATE(i), i === 1) + sel(Q.A_SHIFT(i), shifts, i === 1);
  h += `<div class="sec"><h3>เวรของอีกฝ่าย (ที่คุณจะรับมา)</h3><p>เว้นว่างทั้งหมด = ฝากเวร (ยกเวรของคุณให้อีกฝ่ายโดยไม่รับเวรกลับ)</p></div>`;
  for (let j = 1; j <= ctx.MAX_SLOTS; j++) h += date(Q.B_DATE(j)) + sel(Q.B_SHIFT(j), shifts);
  h += `<div class="q"><label>${Q.NOTE}</label><textarea rows="3"></textarea></div><button>ส่ง</button>`;
  return wrap('Form mock', `<style>.card{max-width:640px;margin:24px auto;background:#fff;border-radius:8px;padding:24px;border-top:10px solid #673ab7}.q{margin:14px 0}label{display:block;font-weight:500;margin-bottom:6px}select,input,textarea{width:100%;padding:8px;font-size:14px;box-sizing:border-box}.req{color:#d93025}.sec{background:#f3e8ff;margin:20px -24px;padding:12px 24px}.sec h3{margin:0 0 4px}.sec p{margin:0;color:#555;font-size:13px}button{background:#673ab7;color:#fff;border:0;padding:10px 24px;border-radius:4px;font-size:14px}</style>
<div class="card"><h2>ER แลกเวร</h2><p style="color:#555;font-size:13px;white-space:pre-line">ยื่นคำขอแลก/ฝากเวร attending ER — ระบบจะตรวจว่าเป็นเจ้าของเวรจริง แล้วส่งอีเมลให้อีกฝ่ายกดตกลง ครบแล้วจึงแก้ตารางเวรให้อัตโนมัติ
แลกได้หลายเวรในคำขอเดียว (สูงสุด ${ctx.MAX_SLOTS} เวรต่อฝั่ง) — อีกฝ่ายจะตกลง/ปฏิเสธทั้งชุดในครั้งเดียว</p><p style="font-size:13px;color:#888">✉ norawit29@gmail.com <i>(verified — Google Form จะแสดงเอง)</i></p>${h}</div>`);
}

const routes = {
  '/': () => wrap('index', `<div class="mail"><h2>ER แลกเวร — UI preview</h2><p>ทุกหน้า render จากโค้ดจริงใน Code.gs (summaryHtml_, buttonsHtml_, page_) — ยกเว้น Form ที่เป็น mock ตาม buildQuestions_ (ของจริงคือ Google Form)</p><ol>
<li><a href="/form">Form (mock)</a></li><li><a href="/email/a">อีเมลยืนยันถึง A</a></li><li><a href="/email/b">อีเมลถึง B (มีปุ่ม)</a></li><li><a href="/email/give">อีเมลฝากเวร</a></li>
<li><a href="/exec?a=approve">หน้า web app: สำเร็จ</a> / <a href="/exec?a=reject">ปฏิเสธ</a> / <a href="/exec?a=done">กดซ้ำ</a> / <a href="/exec?a=fail">error</a></li>
<li><a href="/email/committed">อีเมลสำเร็จ</a> / <a href="/email/error">อีเมล error</a> / <a href="/email/expired">อีเมลหมดอายุ</a></li></ol></div>`),
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

const PORT = process.env.PORT || 3456;
http.createServer((req, res) => {
  const u = new URL(req.url, 'http://localhost');
  const h = routes[u.pathname];
  res.writeHead(h ? 200 : 404, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(h ? h(u.searchParams) : 'not found');
}).listen(PORT, () => console.log(`UI preview: http://localhost:${PORT}`));
