// ---------- table ----------
// Each column draws its own cell. `more: true` columns are hidden until "More columns" is pressed, so the default
// table fits a laptop screen without sideways scrolling and the sparkline stays visible.
const pctCell = k => r => el('td', 'n ' + sgnCls(r[k]), pct(r[k]));
const COLS = [
  {k: 't', l: 'Stock', cls: 'l', dir: 1, cell: r => {
    const c0 = el('td', 'l'), tk = el('div', 'tk'), tb = el('button', 'tkbtn'); tb.type = 'button'; tb.setAttribute('aria-expanded', String(S.open === r.t));
    tb.setAttribute('aria-label', r.t + ', ' + r.name + ': show details'); tb.append(el('span', 'caret', '›'), document.createTextNode(r.t)); tk.append(tb);
    if (vw(r).rank === 4 && wasQualityDip(r) === false) { const nb = el('span', 'new', 'NEW'); nb.dataset.testid = 'new-badge'; tk.append(nb); }
    c0.append(tk, el('div', 'nm', `${r.name} · ${r.region}`));
    const et = earnTag(r); if (et) c0.append(et); const pt = partialTag(r); if (pt) c0.append(' ', pt);
    return c0; }},
  {k: 'price', l: 'Price', dir: -1, cell: r => { const td = el('td', 'n', r.price == null ? '–' : r.price.toFixed(2)); if (r.ccy) td.append(el('span', 'nm', ' ' + r.ccy)); return td; }},
  {k: 'r1', l: '1d', dir: 1, cell: pctCell('r1')}, {k: 'r5', l: '5d', dir: 1, cell: pctCell('r5')},
  {k: 'x5', l: '5d vs index', dir: 1, cell: pctCell('x5'), tip: 'The stock’s 5-day move minus its own country’s (or region’s) index move'},
  {k: 'res5', l: '5d vs index, beta-adjusted (residual)', h: '5d vs index (β-adj.)', wrap: true, dir: 1, more: true, cell: pctCell('res5'), tip: 'The 5-day move left over after removing the index move, scaled by the stock’s usual sensitivity to it (beta). Beta is estimated from the previous year, excluding the last 5 days.'},
  {k: 'r21', l: '1m', dir: 1, more: true, cell: pctCell('r21')},
  {k: 'dd52', l: 'vs 52w high', dir: 1, cell: pctCell('dd52')}, {k: 'vs200', l: 'vs 200d avg', dir: 1, more: true, cell: pctCell('vs200')},
  {k: 'rsi', l: 'RSI', dir: 1, cell: r => el('td', 'n ' + (r.rsi != null && r.rsi < 30 ? 'down' : ''), r.rsi == null ? '–' : r.rsi.toFixed(0))},
  {k: 'volx', l: 'Vol ×', dir: -1, more: true, tip: 'Latest volume divided by the average of the previous 20 days', cell: r => el('td', 'n ' + (r.volx != null && r.volx >= 2 ? '' : 'muted'), r.volx == null ? '–' : r.volx.toFixed(1) + '×')},
  {k: 'q', l: 'Quality score', cls: 'l', dir: -1, tip: 'Share of the scored checks that passed (see Definitions). Bars: filled = passed, hatched = no data.', cell: r => {
    const tq = el('td', 'l n'); tq.append(document.createTextNode(r.q == null ? '–' : String(r.q)), qnote(r), qmeter(r)); return tq; }},
  {k: 'setup', l: 'Setup', cls: 'l', dir: -1, cell: r => {
    const tb = el('td', 'l'); tb.append(badge(r)); return tb; }},
  {k: 'spark', l: '90 days', nosort: true, cell: r => { const td = el('td'); td.append(spark(r.spark)); return td; }},
];
const visCols = () => COLS.filter(c => !c.more || S.more);
function earnText(r, which) {
  const e = r.earn; if (!e) return '–'; if (!e[which]) return 'unknown';
  const d = which === 'last' ? e.days_since_last : e.days_until_next;
  const dt = new Date(e[which] + 'T12:00:00'), short = dt.getDate() + ' ' + dt.toLocaleString('en-GB', {month: 'short'});
  return short + (d == null ? '' : which === 'last' ? ' · ' + d + 'd ago' : ' · in ' + d + 'd') + (e.estimated ? ' (est.)' : '');
}
function partialTag(r) {
  if (!r.partial) return null;
  const t = el('span', 'earn', 'Intraday bar');
  t.title = 'The last bar is dated today and the session may still be open, so this stock’s numbers can change by the close.';
  return t;
}
function earnTag(r) {
  const e = r.earn; if (!e || (e.label !== 'reported_recently' && e.label !== 'reports_soon')) return null;
  const recent = e.label === 'reported_recently', d = recent ? e.days_since_last : e.days_until_next;
  const t = el('span', 'earn', recent ? (d === 0 ? 'Earnings today' : 'Earnings ' + d + 'd ago') : (d === 0 ? 'Earnings today' : 'Earnings in ' + d + 'd'));
  t.title = (recent ? 'Last report ' + e.last : 'Next report ' + e.next) + (e.stale ? ' (older data: the latest refresh failed)' : '') + '. Dates come from a free source and can be off by a day.';
  return t;
}
function spark(v) {
  const w = 78, h = 26, mn = Math.min(...v), mx = Math.max(...v), rg = mx - mn || 1;
  const svg = sv('svg', {width: w, height: h, viewBox: `0 0 ${w} ${h}`, 'aria-hidden': 'true'});
  const pts = v.map((y, i) => [(i / (v.length - 1)) * (w - 4) + 1, h - 3 - ((y - mn) / rg) * (h - 6)]);
  sv('path', {d: 'M' + pts.map(p => p.join(',')).join('L') + `L${pts.at(-1)[0]},${h}L1,${h}Z`, fill: 'var(--sunken)', stroke: 'none'}, svg);
  sv('polyline', {points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: 'var(--ink-2)', 'stroke-width': 1.4}, svg);
  const end = pts.at(-1), dn = v.at(-1) < v[0]; sv('circle', {cx: end[0], cy: end[1], r: 2.6, fill: dn ? 'var(--down)' : 'var(--up)', class: 'enddot', 'data-dir': dn ? 'down' : 'up'}, svg);
  return svg;
}
function qnote(r) {   // '4/6' beside the score when fewer than six checks could be scored
  const used = r.q_scored ?? r.qchecks.filter(c => c.ok !== null).length, of = r.q_applicable ?? 6, s = el('span', 'qn', used < of ? used + '/' + of : '');
  if (used < of) s.title = 'Scored on ' + used + '/' + of + ': the other checks have no data; the score is the share of the scored checks that passed.';
  return s;
}
function qmeter(r) { const s = el('span', 'qm'); r.qchecks.forEach(c => s.append(el('i', c.ok === true ? 'ok' : c.ok === null ? 'na' : ''))); const used = r.qchecks.filter(c => c.ok !== null).length; s.title = r.qchecks.filter(c => c.ok).length + ' of ' + used + ' checks passed' + (used < 6 ? ' (' + (6 - used) + ' with no data or not applicable)' : ''); return s; }

function render() {
  const win = $('win').value, W = WIN[win];
  const isAny = win === 'any';
  // 'Default rules' combines three measures with three different limits, so one slider cannot drive it:
  // the slider is hidden there and a note names the limits. Pick a single window to filter by a drop of your own.
  $('droplab').hidden = isAny; $('dropnote').hidden = !isAny;
  if (isAny) $('dropnote').textContent = `Default rules: 1 day ${MINUS}${(ST.dip.drop_1d * 100).toFixed(0)}%, 5 days ${MINUS}${(ST.dip.drop_5d * 100).toFixed(0)}%, or ${(ST.dip.drawdown_20d * 100).toFixed(0)}% under the 20-day high. Choose one window above to set your own minimum drop.`;
  $('dropv').textContent = MINUS + $('drop').value + '%'; $('qv').textContent = $('qmin').value;
  $('drop').setAttribute('aria-valuetext', 'minimum drop ' + MINUS + $('drop').value + ' percent on ' + W.noun);
  // One label per row under the current controls. A row whose label cannot be worked out is left out and named in the alert.
  const all = rows.filter(r => guard('the screen label', () => { VIEW.set(r, setupOf(r, r)); return true; }, r.t));
  guard('Today in brief', () => brief(all)); guard('the summary tiles', () => tiles(all)); guard('the filter summary', ctlSummary);
  if (!alertsPanel.done) { guard('the trigger alerts', alertsPanel); alertsPanel.done = true; }
  const qs = $('q').value.trim().toLowerCase();
  const pass = (r, o = {}) => {                      // o overrides one filter, to count "what would I get if I picked this option"
    const region = o.region ?? S.region, show = o.show ?? S.show;
    if (region && r.region !== region) return false;
    if (qs && !(r.t.toLowerCase().includes(qs) || r.name.toLowerCase().includes(qs))) return false;
    if ($('hideknife').checked && r.knife) return false;
    if (show === 'quality') return vw(r).rank === 4;
    if (show === 'dips') return vw(r).rank > 0;
    return true;
  };
  const list = all.filter(r => pass(r));
  ['show', 'region'].forEach(id => document.querySelectorAll('#' + id + ' button').forEach(b => {   // live counts beside each option
    const n = all.filter(r => pass(r, {[id]: b.dataset.v})).length;
    b.replaceChildren(b.dataset.label, el('span', 'ct', String(n)));
    b.setAttribute('aria-label', `${b.dataset.label}, ${n} stock${n === 1 ? '' : 's'}`);
  }));
  activeChips();
  list.sort((a, b) => {
    if (!S.sortKey) {                               // default order = size of the drop (biggest first), not the quality score
      const m = W.hist || win, x = a[m], y = b[m];
      if (x == null || y == null) return x == null ? (y == null ? a.t.localeCompare(b.t) : 1) : -1;
      return (x - y) || a.t.localeCompare(b.t);
    }
    const k = S.sortKey, d = S.sortDir;
    if (k === 't') return d * a.t.localeCompare(b.t);
    const x = k === 'setup' ? vw(a).rank : a[k], y = k === 'setup' ? vw(b).rank : b[k];
    if (x == null) return 1; if (y == null) return -1; return d * (x - y);
  });
  $('sortnote').hidden = !!S.sortKey;               // the note describes the default order only
  $('tabletitle').textContent = {quality: 'Dips meeting the check thresholds', dips: 'All dips', all: 'All stocks'}[S.show] + ` · ${list.length}`;
  S.list = list;
  // Phone cards (first 10) and desktop rows (first 25), then a "Show all" button; both share S.showAll. Any change of filter or sort folds the list back.
  const sig = JSON.stringify([S.show, S.region, qs, $('hideknife').checked, $('qmin').value, win, $('drop').value, S.sortKey, S.sortDir]);
  if (sig !== S.sig) { S.sig = sig; S.showAll = false; }

  const head = $('head'); head.replaceChildren();
  $('body').parentElement.classList.toggle('wide', S.more);
  $('colbtn').setAttribute('aria-pressed', String(S.more)); $('colbtn').textContent = S.more ? 'Fewer columns' : 'More columns';
  visCols().forEach(c => {
    const th = el('th', (c.cls || '') + (c.nosort ? '' : ' sortable') + (c.wrap ? ' hw' : ''), c.h || c.l);
    if (c.tip) th.title = (c.tip || '') + (c.h ? (c.tip ? ' ' : '') + 'Full name: ' + c.l + '.' : '');
    if (S.sortKey === c.k) th.append(el('span', 'arr', S.sortDir > 0 ? ' ▲' : ' ▼'));
    if (!c.nosort) {
      th.tabIndex = 0;
      th.setAttribute('aria-sort', S.sortKey === c.k ? (S.sortDir > 0 ? 'ascending' : 'descending') : 'none');
      th.dataset.k = c.k; th.onclick = th.onkeydown = e => { if (e.type === 'keydown' && e.key !== 'Enter' && e.key !== ' ') return; if (e.type === 'keydown') e.preventDefault(); S.sortDir = S.sortKey === c.k ? -S.sortDir : c.dir; S.sortKey = c.k; S.focus = 'th[data-k="' + c.k + '"]'; render(); };
    }
    head.append(th);
  });

  const body = $('body'); body.replaceChildren(); $('empty').hidden = list.length > 0;
  // The desktop table rows are built only on desktop and the phone cards only on phone, so a 348-stock page does not carry the hidden layout.
  if (!mq.matches) visibleOf(list).forEach(r => guard('table row', () => {     // a row that cannot be drawn is skipped and named, never silent
    const tr = el('tr', 'row' + (S.open === r.t ? ' open' : '')); tr.dataset.t = r.t;
    visCols().forEach(c => { const td = c.cell(r); td.dataset.k = c.k; tr.append(td); });
    tr.onclick = () => { S.open = S.open === r.t ? null : r.t; S.focus = 'tr.row[data-t="' + r.t + '"] .tkbtn'; render(); };
    body.append(tr);
    if (S.open === r.t && !mq.matches) { const d = el('tr'); const td = el('td', 'detail'); td.colSpan = visCols().length; const dw = el('div', 'dwrap'); dw.append(safeDetail(r)); td.append(dw); d.append(td); body.append(d); }
  }, r.t));
  guard('the phone cards', () => renderCards(list));
  guard('the show-all button', () => renderRowsMore(list));
  fitScroll();
  syncSort();
  if (S.focus) { const f = document.querySelector(S.focus); S.focus = null; if (f) f.focus(); }
  $('tablehint').textContent = mq.matches ? 'Tap a stock for details. Mini chart: last 90 days, each on its own scale.' : 'Click a row for details. Click a column to sort. Mini chart: last 90 days, each row scaled to its own low and high.';
  guard('the distribution chart', () => hist(all)); guard('the sector chart', () => sectors(all));
}
// Sticky header. While the table fits the card it is not a scroller and `position: sticky` follows the page scroll.
// Wider than the card (More columns, narrow windows): the box scrolls sideways (.hs), and the header is pinned by JS with --pin.
const scrollBox = document.querySelector('.scroll');
function pinHead() {
  if (!scrollBox.classList.contains('hs')) { scrollBox.style.removeProperty('--pin'); return; }
  const t = scrollBox.querySelector('table').getBoundingClientRect(), h = $('head').offsetHeight;
  scrollBox.style.setProperty('--pin', Math.round(Math.min(Math.max(0, -t.top), Math.max(0, t.height - h))) + 'px');
}
function fitScroll() {
  scrollBox.classList.remove('hs');
  scrollBox.style.setProperty('--boxw', scrollBox.clientWidth + 'px');
  if (!mq.matches && scrollBox.querySelector('table').getBoundingClientRect().width > scrollBox.parentElement.clientWidth + 1) scrollBox.classList.add('hs');
  pinHead();
}
let pinQueued = false;
addEventListener('scroll', () => { if (pinQueued) return; pinQueued = true; requestAnimationFrame(() => { pinQueued = false; pinHead(); }); }, {passive: true});
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (window.__dipDrawn) fitScroll(); });
mq.addEventListener('change', () => render());
// Charts are sized to the window when drawn, so redraw after a resize. Width changes only: a phone's address bar showing or
// hiding while scrolling changes the height, and that must not redraw (it would also close nothing, but it costs time).
let lastW = innerWidth, resizeT = 0;
addEventListener('resize', () => { if (innerWidth === lastW) return; clearTimeout(resizeT); resizeT = setTimeout(() => { if (innerWidth === lastW) return; lastW = innerWidth; render(); }, 150); });

