try {
const rows = DATA.rows, ST = DATA.settings;
const MINUS = '−';
const NS = 'http://www.w3.org/2000/svg';
const sv = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
function pct(v, d = 1, sign = true) { if (v == null || !isFinite(v)) return '–'; const s = (Math.abs(v) * 100).toFixed(d) + '%'; return v < 0 ? MINUS + s : (sign && v > 0 ? '+' + s : s); }
function big(v) { if (v == null || !isFinite(v)) return '–'; const a = Math.abs(v), s = a >= 1e12 ? (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? (a / 1e9).toFixed(1) + 'B' : (a / 1e6).toFixed(0) + 'M'; return (v < 0 ? MINUS : '') + s; }
const sgnCls = v => v == null || !isFinite(v) || Math.abs(v) < 5e-4 ? '' : v < 0 ? 'down' : 'up';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function fmtDay(iso) { if (!iso) return '–'; const d = new Date(iso + 'T00:00:00Z'); return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getUTCDay()] + ' ' + d.getUTCDate() + ' ' + MON[d.getUTCMonth()]; }

// ---------- windows the drop can be measured over ----------
const WIN = {
  any:  {label: 'Default rules (1d, 5d or 20d high)', def: ST.dip.drop_5d, n: 5, step: .02, noun: '5-day move', hist: 'r5'},
  r1:   {label: '1 day',             def: ST.dip.drop_1d,        n: 1,  step: .01, noun: '1-day move'},
  r5:   {label: '5 days',            def: ST.dip.drop_5d,        n: 5,  step: .02, noun: '5-day move'},
  r21:  {label: '1 month (21d)',     def: 0.10,                  n: 21, step: .04, noun: '1-month move'},
  dd20: {label: 'From 20-day high',  def: ST.dip.drawdown_20d,   n: 20, step: .04, noun: 'distance from the 20-day high'},
};
Object.entries(WIN).forEach(([k, w]) => { const o = el('option', null, w.label); o.value = k; $('win').append(o); });
$('win').value = 'any';
$('drop').value = Math.round(ST.dip.drop_5d * 100);
$('qmin').value = ST.quality.min_score;

const mq = window.matchMedia('(max-width:600px)');
const regions = [...new Set(rows.map(r => r.region))];
const REGION_ORDER = ['US', 'Europe', 'Nordic'];
regions.sort((a, b) => (REGION_ORDER.indexOf(a) + 1 || 99) - (REGION_ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b));
[['', 'All'], ...regions.map(r => [r, r])].forEach(([v, l], i) => { const b = el('button', null, l); b.dataset.v = v; b.setAttribute('aria-pressed', String(i === 0)); $('region').append(b); });

const S = {show: 'dips', region: '', sortKey: null, sortDir: 1, open: null, more: false};

