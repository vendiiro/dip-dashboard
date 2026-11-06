// ---------- row detail ----------
const drawFail = what => el('div', 'drawfail', what + ' could not be drawn from the data file. The message at the top of the page names the problem.');
const safeDetail = r => guard('the details', () => detail(r), r.t) || drawFail('The details for this stock');
const QFMT = {
  returnOnEquity: v => pct(v, 1, false), profitMargins: v => pct(v, 1, false), debtToEquity: v => v.toFixed(0) + '%',
  freeCashflow: (v, r) => big(v) + (r.ccy ? ' ' + r.ccy : ''), revenueGrowth: v => pct(v, 1), marketCap: v => big(v) + ' USD',
};
function detail(r) {
  const wrap = el('div');
  if (r.why && r.why.length) { const w = el('div', 'whystrip'); w.append(el('b', null, 'Flagged because')); r.why.forEach(x => w.append(el('span', null, x))); wrap.append(w); }
  const g = el('div', 'dgrid'); wrap.append(g);
  const p1 = el('div', 'panel'); p1.append(el('h3', null, '1 year · price, 200-day average, 52-week high'), guard('the 1-year chart', () => priceChart(r), r.t) || drawFail('The 1-year chart'));
  const lg = el('div', 'legend');
  [['var(--ink-2)', 'Price'], ['var(--accent)', '200-day average'], ['var(--ink-3)', '52-week high']].forEach(([c, l], i) => { const s = el('span'); const k = el('i'); k.style.borderTopColor = c; if (i) k.style.borderTopStyle = 'dashed'; s.append(k, l); lg.append(s); });
  const sh = el('span'); const k = el('i'); k.style.cssText = 'border:0;width:12px;height:10px;background:var(--down-soft);vertical-align:-1px'; sh.append(k, 'Drop window'); lg.append(sh);
  p1.append(lg); g.append(p1);

  const p2 = el('div', 'panel'); p2.append(el('h3', null, r.q == null ? 'Quality checks · no score' : `Quality checks · ${r.q}/100`));
  { const ev = evidenceNote(r); if (ev) p2.append(el('div', 'nm', ev.charAt(0).toUpperCase() + ev.slice(1) + '.')); }
  const ul = el('ul', 'checks');
  r.qchecks.forEach(c => { const li = el('li'); li.append(el('span', c.ok === true ? 'ok' : c.ok === false ? 'bad' : 'na', c.ok === true ? '✓' : c.ok === false ? '✗' : '?'), el('span', null, c.label), el('span', 'val', c.ok === null ? (c.na ? 'n/a for ' + (r.sector || 'sector') : 'no data') : QFMT[c.key](c.value, r))); ul.append(li); });
  p2.append(ul, el('h3', null, 'Falling-knife checklist'));
  const ul2 = el('ul', 'checks');
  [[r.vs200 != null && r.vs200 < 0, 'Below 200-day average', pct(r.vs200)], [r.s200_falling, '200-day average falling', 'vs 20 days ago'], [r.dd52 != null && r.dd52 <= -ST.knife.drawdown_52w, `≥ ${(ST.knife.drawdown_52w * 100).toFixed(0)}% under 52-week high`, pct(r.dd52)]]
    .forEach(([on, l, v]) => { const li = el('li'); li.append(el('span', on ? 'bad' : 'ok', on ? '●' : '○'), el('span', null, l), el('span', 'val', v)); ul2.append(li); });
  p2.append(ul2, el('div', 'nm', r.knife ? 'All three are true, so this is flagged as a falling knife.' : 'A falling knife needs all three. Filled dots are met.'));

  const p3 = el('div', 'panel'); p3.append(el('h3', null, 'Key numbers'));
  const kv = el('div', 'kv'); const mc = r.qchecks.find(c => c.key === 'marketCap');
  const KEY = ['5d vs index','Forward P/E', 'Trailing P/E', 'Market cap (USD)', 'Sector', 'Next earnings'];   // the rest sits behind "More context"
  [['5d vs index' + (r.idx ? ' (' + r.idx + ')' : r.x5 == null && r.idx_why ? ' (' + r.idx_why + ')' : ''), r.x5 == null ? '–' : pct(r.x5)], ['Forward P/E', r.fpe == null ? '–' : r.fpe.toFixed(1)], ['Trailing P/E', r.tpe == null ? '–' : r.tpe.toFixed(1)],
   ['Market cap (USD)', mc && mc.value != null ? big(mc.value) : '–'], ['Sector', r.sector || '–'], ['From 20-day high', pct(r.dd20)], ['5d move in standard deviations', r.z5 == null ? '–' : r.z5.toFixed(1)],
   ['5d beyond market (beta-adjusted)', r.res5 == null ? '–' : pct(r.res5) + NOT_ADJ(r)], ['5d beyond market (beta-adjusted), in standard deviations', r.res5z == null ? '–' : r.res5z.toFixed(1)],
   ['Beta' + (r.beta_side === 'cap' ? ' (capped at 3)' : r.beta_side === 'floor' ? ' (floored at 0)' : ''), r.beta == null ? '–' : r.beta.toFixed(2) + (r.beta_side && r.beta_raw != null ? ' (est. ' + r.beta_raw.toFixed(2) + ')' : '') + (r.beta_se != null ? ' ±' + r.beta_se.toFixed(2) : '')],
   ['Last earnings', earnText(r, 'last')], ['Next earnings', earnText(r, 'next')]]
    .forEach(([a, b]) => { const keep = KEY.some(k => a.startsWith(k)) && !a.includes('beta-adjusted'); const row = el('div', keep ? 'kvx' : 'kvx extra'); row.append(el('span', null, a), el('span', null, b)); if (!keep) row.hidden = true; kv.append(row); });
  p3.append(kv);
  { const more = el('button', 'more', 'More context'); more.type = 'button'; more.setAttribute('aria-expanded', 'false');
    more.onclick = e => { e.stopPropagation(); const ex = more.getAttribute('aria-expanded') !== 'true'; more.setAttribute('aria-expanded', String(ex)); kv.querySelectorAll('.extra').forEach(x => { x.hidden = !ex; }); more.textContent = ex ? 'Less context' : 'More context'; };
    p3.append(more); }
  if (r.res5 != null && r.mkt_adj === false) p3.append(el('div', 'foot', 'Beta was capped, floored or uncertain, so this number is rough; compare it with the plain 5d vs index.'));
  if (r.res5 == null && r.res_why) p3.append(el('div', 'foot', 'No residual: ' + r.res_why + '.'));
  if (r.earn && r.earn.note && (r.earn.stale || r.earn.error || !r.earn.last || !r.earn.next || /scheduled date passed/.test(r.earn.note))) p3.append(el('div', 'foot', 'Earnings dates: ' + r.earn.note));
  g.append(p3, p2);

  // Headlines sit under the chart so the wide chart column is not left empty; first 3 shown, the rest behind a toggle.
  p1.append(el('h3', null, 'Headlines · read before deciding'));
  const nl = el('ul', 'news');
  if (r.news.length) nl.append(el('li', 'src', 'Found by a Yahoo search on the ticker. They can be about the wider market, not about why this stock moved.'));
  const items = r.news.map(n => {
    const li = el('li');
    if (/^https?:\/\//.test(n.url)) { const a = el('a', null, n.title); a.href = n.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; li.append(a); } else li.append(el('div', null, n.title));
    if (n.src) li.append(el('div', 'src', n.src)); nl.append(li); return li;
  });
  if (!r.news.length) nl.append(el('li', 'src', 'No headlines found. They are looked up only for stocks with a notable drop, and the free source often has none for non-US companies.'));
  items.forEach((li, i) => { if (i >= 3) li.hidden = true; });
  p1.append(nl);
  if (items.length > 3) {
    const lab = ex => ex ? 'Show fewer headlines' : `Show ${items.length - 3} more headline${items.length - 3 === 1 ? '' : 's'}`;
    const more = el('button', 'more', lab(false)); more.type = 'button';
    more.setAttribute('aria-expanded', 'false');
    more.onclick = e => { e.stopPropagation(); const ex = more.getAttribute('aria-expanded') !== 'true'; more.setAttribute('aria-expanded', String(ex)); items.forEach((li, i) => { if (i >= 3) li.hidden = !ex; }); more.textContent = lab(ex); };
    p1.append(more);
  }
  return wrap;
}
