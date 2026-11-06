// Chart width in px: the drawing is as wide as the space it gets, so text keeps its size on a phone.
const chartW = (max, reserve) => Math.max(260, Math.min(max, innerWidth - reserve));

// ---------- tooltip ----------
const tip = $('tip');
function showTip(e, nodes) { tip.replaceChildren(...nodes); tip.hidden = false; const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8), y = Math.min(e.clientY + 14, innerHeight - tip.offsetHeight - 8); tip.style.left = x + 'px'; tip.style.top = y + 'px'; }
const hideTip = () => { tip.hidden = true; };

function priceChart(r) {
  // hist has no dates of its own: item i sits on DATA.chart_dates[hist.o + i], prices are integer hundredths (DATA.price_scale).
  // A null close is an axis day without a bar for this stock (a holiday): it is dropped, so the chart draws the same points as before.
  const H_ = r.hist, sc = DATA.price_scale || 1, keep = [];
  H_.c.forEach((v, i) => { if (v != null) keep.push(i); });
  const pick = a => keep.map(i => a[i] == null ? null : a[i] / sc);
  const c = pick(H_.c), s = pick(H_.s), hi = pick(H_.h), DD = keep.map(i => DATA.chart_dates[H_.o + i]);
  const W = chartW(620, mq.matches ? 90 : 120), H = mq.matches ? 210 : 260, pl = 8, pr = 52, pt = 22, pb = 22, n = c.length;
  const all = [...c, ...s.filter(v => v != null), ...hi.filter(v => v != null)], mn = Math.min(...all) * .98, mx = Math.max(...all) * 1.01;
  const X = i => pl + i / (n - 1) * (W - pl - pr), Y = v => pt + (1 - (v - mn) / (mx - mn)) * (H - pt - pb);
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, width: W, role: 'img', 'aria-label': `${r.t} one-year price chart`});
  sv('text', {x: W - 2, y: 11, 'text-anchor': 'end', class: 'axcap'}, svg).textContent = 'Price' + (r.ccy ? ', ' + r.ccy : '');   // axis caption
  for (let k = 0; k <= 3; k++) { const v = mn + (mx - mn) * k / 3; sv('line', {x1: pl, x2: W - pr, y1: Y(v), y2: Y(v), class: 'tick'}, svg); sv('text', {x: W - pr + 6, y: Y(v) + 4}, svg).textContent = v >= 100 ? v.toFixed(0) : v.toFixed(1); }
  let last = '';
  DD.forEach((d, i) => { const m = d.slice(5, 7); if (m !== last && i > 8 && i < n - 8 && (+m % 3 === 1)) sv('text', {x: X(i), y: H - 6, 'text-anchor': 'middle'}, svg).textContent = MON[+m - 1] + ' ' + d.slice(2, 4); last = m; });
  const span = Math.min(WIN[$('win').value].n, n - 1);   // 'any' shades the last 5 days
  sv('rect', {x: X(n - 1 - span), y: pt, width: X(n - 1) - X(n - 1 - span) + 2, height: H - pt - pb, fill: 'var(--down-soft)'}, svg);
  const line = (arr, attrs) => sv('path', {d: arr.map((v, i) => v != null ? (i && arr[i - 1] != null ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(v).toFixed(1) : '').join(''), fill: 'none', ...attrs}, svg);
  line(hi, {stroke: 'var(--ink-3)', 'stroke-width': 1.2, 'stroke-dasharray': '2 3'});
  line(s, {stroke: 'var(--accent)', 'stroke-width': 1.6, 'stroke-dasharray': '5 3'});
  line(c, {stroke: 'var(--ink-2)', 'stroke-width': 1.8});
  const dn = c[n - 1] < c[0];      // same rule as the sparkline: lower than a year ago is red, otherwise blue
  sv('circle', {cx: X(n - 1), cy: Y(c[n - 1]), r: 4, fill: dn ? 'var(--down)' : 'var(--up)', stroke: 'var(--surface)', 'stroke-width': 2, class: 'enddot', 'data-dir': dn ? 'down' : 'up'}, svg);
  const cross = sv('line', {y1: pt, y2: H - pb, stroke: 'var(--ink-3)', 'stroke-width': 1, visibility: 'hidden'}, svg);
  const dot = sv('circle', {r: 3.5, fill: 'var(--ink)', visibility: 'hidden'}, svg);
  const hit = sv('rect', {x: pl, y: 0, width: W - pl - pr, height: H, fill: 'transparent'}, svg);
  const fmt = v => v == null ? '–' : v.toFixed(2) + (r.ccy ? ' ' + r.ccy : '');
  hit.addEventListener('mousemove', e => {
    const b = svg.getBoundingClientRect(), x = (e.clientX - b.left) * W / b.width, i = Math.max(0, Math.min(n - 1, Math.round((x - pl) / (W - pl - pr) * (n - 1))));
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('visibility', 'visible');
    dot.setAttribute('cx', X(i)); dot.setAttribute('cy', Y(c[i])); dot.setAttribute('visibility', 'visible');
    showTip(e, [el('div', null, DD[i]), el('div', 'num', 'Price ' + fmt(c[i])), el('div', 'num', '200d avg ' + fmt(s[i])), el('div', 'num', 'vs 52w high ' + (hi[i] ? pct(c[i] / hi[i] - 1) : '–'))]);
  });
  hit.addEventListener('mouseleave', () => { cross.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); hideTip(); });
  return svg;
}

// ---------- distribution of the chosen window ----------
function hist(all) {
  const win = $('win').value, W_ = WIN[win], key = W_.hist || win, any = win === 'any';
  const thr = any ? -ST.dip.drop_5d : -(+$('drop').value) / 100;
  const vals = all.map(r => r[key]).filter(v => v != null);
  $('histtitle').textContent = 'Where the ' + W_.noun + ' sits';
  if (!vals.length) { $('hist').replaceChildren(el('div', 'empty', 'No data for this window.')); return; }
  const sorted = [...vals].sort((a, b) => a - b), med = sorted[Math.floor(sorted.length / 2)], step = W_.step;
  $('histcap').textContent = `${W_.noun[0].toUpperCase() + W_.noun.slice(1)} of every screened stock. The median stock is at ${pct(med)}. Red bars are at or past the ${any ? '5-day rule' : 'drop limit you set'} (${pct(thr)}).` +
    (any ? ' Stocks flagged by the 1-day or 20-day-high rule can sit in grey bars.' : '') + ' If the whole distribution has shifted left, the market is selling off broadly.';
  const rawLo = Math.min(...vals, thr), rawHi = Math.max(...vals, 0), every = (rawHi - rawLo) / step > 14 ? 4 : 2, unit = step * every;
  const lo = Math.floor(rawLo / unit + 1e-9) * unit, hi = Math.ceil(rawHi / unit - 1e-9) * unit, bins = [];
  for (let b = lo; b < hi - 1e-9; b += step) bins.push({a: b, b: b + step, items: all.filter(r => r[key] != null && r[key] >= b - 1e-12 && r[key] < b + step - 1e-12)});
  if (bins.length) bins.at(-1).items = all.filter(r => r[key] != null && r[key] >= bins.at(-1).a - 1e-12 && r[key] <= bins.at(-1).b + 1e-12);
  const W = chartW(560, 64), H = 210, pl = 26, pr = 16, pt = 18, pb = 28, mxc = Math.max(1, ...bins.map(b => b.items.length));
  const X = v => pl + (v - lo) / (hi - lo) * (W - pl - pr), Y = k => pt + (1 - k / mxc) * (H - pt - pb);
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, width: W, role: 'img', 'aria-label': 'Histogram of moves'});
  for (let k = 0; k <= mxc; k += Math.max(1, Math.ceil(mxc / 4))) { sv('line', {x1: pl, x2: W - pr, y1: Y(k), y2: Y(k), class: 'tick'}, svg); sv('text', {x: pl - 6, y: Y(k) + 4, 'text-anchor': 'end'}, svg).textContent = k; }
  bins.forEach(b => {
    if (!b.items.length) return;
    const dip = b.b <= thr + 1e-9;
    const rc = sv('rect', {x: X(b.a) + 1, y: Y(b.items.length), width: Math.max(1, X(b.b) - X(b.a) - 2), height: H - pb - Y(b.items.length), rx: 2, fill: dip ? 'var(--down)' : 'var(--neutral-bar)'}, svg);
    rc.addEventListener('mousemove', e => showTip(e, [el('div', null, `${pct(b.a, 0)} to ${pct(b.b, 0)} · ${b.items.length} stock${b.items.length === 1 ? '' : 's'}`), el('div', 'num', b.items.map(x => x.t).join(', '))]));
    rc.addEventListener('mouseleave', hideTip);
  });
  for (let v = lo; v <= hi + 1e-9; v += unit) sv('text', {x: X(v), y: H - 8, 'text-anchor': 'middle'}, svg).textContent = pct(Math.round(v * 100) / 100, 0, false).replace(/^−0%$/, '0%');
  sv('line', {x1: pl, x2: W - pr, y1: H - pb, y2: H - pb, class: 'axis'}, svg);
  const mark = (v, label, col, anchor) => { sv('line', {x1: X(v), x2: X(v), y1: pt - 6, y2: H - pb, stroke: col, 'stroke-width': 1.5, 'stroke-dasharray': '4 3'}, svg); sv('text', {x: X(v) + (anchor === 'end' ? -5 : 5), y: pt - 2, 'text-anchor': anchor, style: 'fill:var(--ink-2)'}, svg).textContent = label; };
  const farApart = Math.abs(X(thr) - X(med)) > 70;
  mark(thr, any ? '5-day rule' : 'drop limit', 'var(--down)', 'end'); mark(med, 'median stock', 'var(--ink-2)', farApart || med > thr ? 'start' : 'end');
  $('hist').replaceChildren(svg);
}

// ---------- sectors ----------
function sectors(all) {
  const tot = {}, dip = {};
  all.forEach(r => { const s = r.sector || 'Other'; tot[s] = (tot[s] || 0) + 1; if (vw(r).rank > 0) dip[s] = (dip[s] || 0) + 1; });
  const list = Object.keys(dip).sort((a, b) => dip[b] - dip[a] || a.localeCompare(b));
  if (!list.length) { $('sect').replaceChildren(el('div', 'empty', 'No stocks are flagged as a dip with the current settings.')); return; }
  const rowH = 26, W = chartW(440, 64), lab = 110, H = list.length * rowH + 4, mx = Math.max(...list.map(s => dip[s]));
  const svg = sv('svg', {viewBox: `0 0 ${W} ${H}`, width: W, role: 'img', 'aria-label': 'Dips by sector'});
  list.forEach((s, i) => {
    const y = i * rowH + 3, w = (W - lab - 90) * dip[s] / mx;
    sv('text', {x: lab - 8, y: y + 15, 'text-anchor': 'end', style: 'fill:var(--ink-2);font-size:12px'}, svg).textContent = s;
    const rc = sv('rect', {x: lab, y: y + 3, width: Math.max(w, 3), height: rowH - 10, rx: 3, fill: 'var(--accent)'}, svg);
    sv('text', {x: lab + w + 6, y: y + 15, style: 'fill:var(--ink);font-size:12px'}, svg).textContent = String(dip[s]);
    sv('text', {x: lab + w + 22, y: y + 15, style: 'font-size:11px'}, svg).textContent = `of ${tot[s]}`;
    rc.addEventListener('mousemove', e => showTip(e, [el('div', null, s), el('div', 'num', all.filter(x => (x.sector || 'Other') === s && vw(x).rank > 0).map(x => x.t).join(', '))]));
    rc.addEventListener('mouseleave', hideTip);
  });
  $('sect').replaceChildren(svg);
}

