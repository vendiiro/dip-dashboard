// ---------- phone layout: one card per stock ----------
function syncSort() {
  const sel = $('sortsel');
  if (!sel.options.length) {
    sel.append(new Option('Size of drop (default)', ''));
    COLS.filter(c => !c.nosort).forEach(c => sel.append(new Option(c.l + (c.k === 't' ? ' (A to Z)' : c.dir === 1 ? ' (low to high)' : ' (high to low)'), c.k)));
    sel.onchange = () => { const c = COLS.find(x => x.k === sel.value); S.sortKey = c ? c.k : null; S.sortDir = c ? c.dir : 1; render(); };
  }
  sel.value = S.sortKey || '';
}
const CARDS_FIRST = 10, ROWS_FIRST = 25;   // phone cards / desktop rows shown before "Show all N stocks"
const capNow = () => mq.matches ? CARDS_FIRST : ROWS_FIRST;
// The rows (or cards) to draw: the first few, or all of them after "Show all"; an open stock outside the first few stays in view.
function visibleOf(list) {
  const shown = S.showAll ? list : list.slice(0, capNow());
  if (S.open && !shown.some(r => r.t === S.open)) { const o = list.find(r => r.t === S.open); if (o) return [...shown, o]; }
  return shown;
}
// The one "Show all N stocks" button for phone and desktop: same state (S.showAll), same style, own test id.
function showAllBtn(testid, list) {
  const cap = capNow(), mb = el('button', 'showall', S.showAll ? 'Show the first ' + cap + ' only' : 'Show all ' + list.length + ' stocks');
  mb.type = 'button'; mb.dataset.testid = testid; mb.setAttribute('aria-expanded', String(!!S.showAll));
  mb.onclick = () => { S.showAll = !S.showAll; render(); const nb = document.querySelector('[data-testid=' + testid + ']'); if (nb) nb.focus(); };
  return mb;
}
function renderRowsMore(list) {
  const box = $('rowsmore'); box.replaceChildren();
  box.hidden = mq.matches || list.length <= ROWS_FIRST;
  if (box.hidden) return;
  box.append(el('span', null, S.showAll ? `Showing all ${list.length} stocks.` : `Showing the first ${ROWS_FIRST} of ${list.length} stocks.`), showAllBtn('rows-more', list));
}
function renderCards(list) {
  const box = $('cards'); box.replaceChildren();
  if (!mq.matches) return;
  visibleOf(list).forEach((r, i) => guard('phone card', () => {
    const open = S.open === r.t, id = 'sc-' + i;
    const card = el('div', 'sc' + (open ? ' open' : ''));
    const b = el('button', 'schead'); b.type = 'button'; b.setAttribute('aria-expanded', String(open)); b.setAttribute('aria-controls', id + '-d');
    const l1 = el('div', 'l1'); const tk = el('div', 'tk'); tk.append(el('span', 'caret', '›'), document.createTextNode(r.t));
    if (vw(r).rank === 4 && wasQualityDip(r) === false) { const nb = el('span', 'new', 'NEW'); nb.dataset.testid = 'new-badge'; tk.append(nb); }
    l1.append(tk, el('div', 'nm', `${r.name} · ${r.region}`));
    const px = el('div', 'px', r.price == null ? '–' : r.price.toFixed(2)); if (r.ccy) px.append(el('span', 'nm', ' ' + r.ccy));
    const mets = el('div', 'mets');
    const m = (lab, txt, cls) => { const d = el('div'); d.append(el('span', 'lab', lab), el('span', 'v ' + (cls || ''), txt)); mets.append(d); };
    m('1d', pct(r.r1), sgnCls(r.r1)); m('5d', pct(r.r5), sgnCls(r.r5));
    const dq = el('div'); dq.append(el('span', 'lab', 'Quality score')); const qv = el('span', 'v', r.q == null ? '–' : String(r.q)); qv.append(qnote(r), qmeter(r)); dq.append(qv); mets.append(dq);
    const sp = el('div'); sp.style.justifySelf = 'end'; sp.append(spark(r.spark)); mets.append(sp);
    const bdrow = el('div', 'bdrow'); bdrow.append(badge(r)); { const et = earnTag(r); if (et) bdrow.append(et); const pt = partialTag(r); if (pt) bdrow.append(pt); }
    b.append(l1, px, mets, bdrow);
    b.onclick = () => { S.open = S.open === r.t ? null : r.t; render(); const nb = document.querySelector('#cards .sc[data-t="' + CSS.escape(r.t) + '"] .schead'); if (nb) nb.focus({preventScroll: true}); };
    card.append(b); card.dataset.t = r.t;
    if (open) { const d = el('div', 'scdetail'); d.id = id + '-d'; d.append(safeDetail(r)); card.append(d); }
    box.append(card);
  }, r.t));
  if (list.length > CARDS_FIRST) box.append(showAllBtn('cards-more', list));
}

