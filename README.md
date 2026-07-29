# coffee-counter
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>咖啡机计数</title>
<style>
  :root {
    --bg1: #160e0a; --bg2: #241712;
    --text: #f3e9e0; --accent: #c8895a; --accent2: #e0a878;
    --muted: rgba(243,233,224,.45);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: linear-gradient(160deg, var(--bg1), var(--bg2));
    color: var(--text);
    display: flex; flex-direction: column; align-items: center;
    min-height: 100vh; padding: 24px 16px 40px;
    user-select: none; -webkit-user-select: none; overflow-x: hidden;
  }
  .stats { display: flex; gap: 30px; margin-bottom: 26px; }
  .stat { text-align: center; }
  .stat .num { font-size: 30px; font-weight: 700; color: var(--accent2); line-height: 1; transition: color .12s, text-shadow .12s, transform .12s; }
  .stat .num.preview { color: #fff; text-shadow: 0 0 14px rgba(224,168,120,.9); transform: scale(1.12); }
  .stat .label { font-size: 12px; color: var(--muted); margin-top: 6px; }

  /* 透明玻璃质感圆圈 */
  .wheel {
    position: relative;
    width: 220px; height: 240px;
    border-radius: 24px;
    background: rgba(255,255,255,.07);
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,.18);
    box-shadow: 0 8px 32px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.15);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    touch-action: none; overflow: hidden;
  }
  .wheel .value {
    font-size: 92px; font-weight: 800; color: #fff;
    line-height: 1; text-shadow: 0 2px 16px rgba(224,168,120,.45);
  }
  .wheel .ghost {
    font-size: 34px; font-weight: 700;
    color: rgba(243,233,224,.28);
    position: absolute; left: 0; right: 0; text-align: center;
    pointer-events: none;
  }
  .wheel .ghost#ghostUp { top: 30px; }
  .wheel .ghost#ghostDown { bottom: 30px; }

  .btns { margin-top: 28px; }
  .confirm {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; cursor: pointer;
    box-shadow: 0 6px 22px rgba(200,137,90,.4), inset 0 1px 2px rgba(255,255,255,.4);
  }
  .confirm:active { transform: scale(.93); filter: brightness(.95); }

  .log { width: 100%; max-width: 420px; margin-top: 30px; }
  .log h3 { font-size: 13px; color: var(--muted); font-weight: 500; margin-bottom: 10px; padding-left: 4px; }
  .empty { color: var(--muted); text-align: center; padding: 20px 0; font-size: 14px; }

  .day { background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);
    border-radius: 12px; margin-bottom: 8px; overflow: hidden; }
  .day-head { display: flex; align-items: center; justify-content: space-between;
    padding: 13px 16px; cursor: pointer; }
  .day-label { font-size: 15px; font-weight: 600; }
  .day-right { display: flex; align-items: center; gap: 10px; }
  .day-cnt { font-size: 15px; font-weight: 700; color: var(--accent2); }
  .arrow { font-size: 11px; color: var(--muted); }
  .detail { border-top: 1px solid rgba(255,255,255,.08); padding: 4px 16px 8px; }
  .drow { display: flex; align-items: center; justify-content: space-between;
    padding: 9px 0; font-size: 14px; color: var(--text); }
  .drow + .drow { border-top: 1px solid rgba(255,255,255,.05); }

  .toast {
    position: fixed; left: 50%; bottom: 30px; transform: translateX(-50%);
    background: var(--accent2); color: #1a0f0a; padding: 10px 20px;
    border-radius: 22px; font-size: 14px; font-weight: 600;
    opacity: 0; pointer-events: none; transition: .25s;
  }
  .toast.show { opacity: 1; }
</style>
</head>
<body>
  <div class="stats">
    <div class="stat"><div class="num" id="sToday">0</div><div class="label">今日杯数</div></div>
    <div class="stat"><div class="num" id="sTotal">0</div><div class="label">累计杯数</div></div>
  </div>

  <div class="wheel" id="wheel">
    <div class="ghost" id="ghostUp"></div>
    <div class="value" id="val">1</div>
    <div class="ghost" id="ghostDown"></div>
  </div>

  <div class="btns">
    <button class="confirm" id="confirmBtn" aria-label="确定填入"></button>
  </div>

  <div class="log">
    <h3>历史记录</h3>
    <div id="list"></div>
  </div>

  <div class="toast" id="toast"></div>

<script>
/* ===== 共享服务器存储：多人联动 ===== */
async function loadRecords() {
  try {
    const r = await fetch('api/records');
    if (!r.ok) return { records: [], stats: { total: 0, today: 0 } };
    const d = await r.json();
    return { records: d.records || [], stats: d.stats || { total: 0, today: 0 } };
  } catch (e) { return { records: [], stats: { total: 0, today: 0 } }; }
}

const MIN = 1, MAX = 99, STEP_PX = 36;
let count = 1;
let baseTotal = 0;
let pressing = false;
const wheel = document.getElementById('wheel');
const valEl = document.getElementById('val');
const ghostUp = document.getElementById('ghostUp');
const ghostDown = document.getElementById('ghostDown');
const sTotalEl = document.getElementById('sTotal');
const expandedDays = new Set();
let _records = [];

function render() {
  valEl.textContent = count;
  ghostUp.textContent = count > MIN ? count - 1 : '';
  ghostDown.textContent = count < MAX ? count + 1 : '';
  updateTotal();
}
function updateTotal() {
  if (pressing) { sTotalEl.textContent = baseTotal + count; sTotalEl.classList.add('preview'); }
  else { sTotalEl.textContent = baseTotal; sTotalEl.classList.remove('preview'); }
}
function setCount(n) {
  n = Math.min(MAX, Math.max(MIN, n));
  if (n === count) return;
  count = n; render();
}

/* 触摸滑动：向上滑数字增大 */
let startY = null, startCount = 1;
wheel.addEventListener('touchstart', e => { startY = e.touches[0].clientY; startCount = count; }, {passive:true});
wheel.addEventListener('touchmove', e => {
  if (startY === null) return;
  const dy = startY - e.touches[0].clientY;
  const t = Math.min(MAX, Math.max(MIN, startCount + Math.round(dy / STEP_PX)));
  if (t !== count) setCount(t);
}, {passive:true});
/* 鼠标拖动（桌面） */
let mDown = false, mStartY = null, mStartCount = 1;
wheel.addEventListener('mousedown', e => { mDown = true; mStartY = e.clientY; mStartCount = count; });
window.addEventListener('mousemove', e => {
  if (!mDown) return;
  const dy = mStartY - e.clientY;
  const t = Math.min(MAX, Math.max(MIN, mStartCount + Math.round(dy / STEP_PX)));
  if (t !== count) setCount(t);
});
window.addEventListener('mouseup', () => { mDown = false; });
/* 滚轮调节 */
wheel.addEventListener('wheel', e => { e.preventDefault(); setCount(count + (e.deltaY < 0 ? 1 : -1)); }, {passive:false});

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1400);
}

function statsOf(recs) {
  const total = recs.reduce((s, r) => s + r.count, 0);
  const today = new Date().toDateString();
  const todayCount = recs.filter(r => new Date(r.time).toDateString() === today)
                        .reduce((s, r) => s + r.count, 0);
  return { total, today: todayCount };
}

async function refresh() {
  const data = await loadRecords();
  _records = data.records;
  baseTotal = data.stats.total;
  document.getElementById('sToday').textContent = data.stats.today;
  updateTotal();
  renderHistory();
}

function fmtDateKey(iso) { const d = new Date(iso); return `${d.getFullYear()}-${d.getMonth()+1}-${d.getDate()}`; }
function fmtDateLabel(iso) {
  const d = new Date(iso);
  const wk = ['日','一','二','三','四','五','六'][d.getDay()];
  return `${d.getMonth()+1}月${d.getDate()}日 周${wk}`;
}
function toggleDay(key) {
  if (expandedDays.has(key)) expandedDays.delete(key); else expandedDays.add(key);
  renderHistory();
}
function renderHistory() {
  const list = document.getElementById('list');
  if (!_records.length) { list.innerHTML = '<div class="empty">还没有记录，转一转圆圈填一笔吧～</div>'; return; }
  const groups = {};
  _records.forEach(r => { const k = fmtDateKey(r.time); (groups[k] = groups[k] || []).push(r); });
  const keys = Object.keys(groups).sort((a,b) => b.localeCompare(a));
  list.innerHTML = keys.map(k => {
    const items = groups[k];
    const dayTotal = items.reduce((s,r) => s + r.count, 0);
    const open = expandedDays.has(k);
    const detail = open ? `<div class="detail">` + items.slice().sort((a,b)=>b.time.localeCompare(a.time)).map(r => {
      const d = new Date(r.time); const p = n => String(n).padStart(2,'0');
      return `<div class="drow"><span>${p(d.getHours())}:${p(d.getMinutes())} · ${r.count} 杯</span>
        <button class="del" onclick="delRec('${r.id}')">删除</button></div>`;
    }).join('') + `</div>` : '';
    return `<div class="day"><div class="day-head" onclick="toggleDay('${k}')">
      <span class="day-label">${fmtDateLabel(items[0].time)}</span>
      <span class="day-right"><span class="day-cnt">${dayTotal} 杯</span>
      <span class="arrow">${open ? '▲' : '▼'}</span></span></div>${detail}</div>`;
  }).join('');
}

async function submit() {
  try {
    const res = await fetch('api/records', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ count })
    });
    if (res.ok) {
      const data = await res.json();
      toast('✓ 已记入 ' + count + ' 杯（累计 ' + data.stats.total + '）');
    } else {
      const err = await res.json().catch(() => ({}));
      toast('✗ ' + (err.error || ('填入失败 ' + res.status)));
    }
  } catch (e) {
    toast('✗ 连不上服务，请确认网络');
  }
  refresh();
}
async function delRec(id) {
  if (!confirm('删除这条记录？')) return;
  await fetch('api/records/' + id, { method: 'DELETE' });
  refresh();
}

/* 按住按钮：累计实时合计预览；松开：提交 */
const confirmBtn = document.getElementById('confirmBtn');
function pressStart() { if (!pressing) { pressing = true; updateTotal(); } }
function pressEnd() { if (pressing) { pressing = false; updateTotal(); submit(); } }
confirmBtn.addEventListener('mousedown', pressStart);
confirmBtn.addEventListener('touchstart', e => { e.preventDefault(); pressStart(); }, {passive:false});
window.addEventListener('mouseup', pressEnd);
confirmBtn.addEventListener('touchend', pressEnd);
confirmBtn.addEventListener('mouseleave', () => { if (pressing) { pressing = false; updateTotal(); } });

render();
refresh();
setInterval(refresh, 3000); // 多人联动：每3秒自动同步
</script>
</body>
</html>
