// ---------- today in brief: a plain-language read of the current screen ----------
// The numbers behind the brief's index sentence and the phone Market tile line: median 5-day move of all screened stocks, and how many
// flagged dips (with an index comparison) fell at least 5 points more than their own index.
function mktFacts(all, dips) {
  const r5s = all.map(r => r.r5).filter(v => v != null).sort((a, b) => a - b);
  const withIdx = dips.filter(r => r.x5 != null);
  return {med: r5s.length ? r5s[Math.floor(r5s.length / 2)] : null, far: withIdx.filter(r => r.x5 <= -0.05).length, n: withIdx.length};
}
function brief(all) {
  const box = $('brief'); box.replaceChildren();
  const dips = all.filter(r => vw(r).rank > 0), qd = dips.filter(r => vw(r).rank === 4);
  const newQ = qd.filter(r => wasQualityDip(r) === false);
  const h = el('h2', null, 'Today in brief'); h.id = 'brief-h';
  h.append(el('span', 'sub'));
  const sub = h.lastChild; sub.append(el('span', 'dot', ' · '), 'a description of the latest close, not a forecast.'); const rest = el('span', 'subrest', ' Dip and quality counts follow the window and quality settings; the rest covers all screened stocks.'); sub.append(rest);
  const p1 = el('p'), dl = el('a', null, 'Definitions'); dl.href = '#def-q';
  p1.append(`${dips.length} of ${all.length} screened stocks are flagged as dips; ${qd.length} of them meet the check thresholds (see `, dl, `)${newQ.length ? ' and ' + newQ.length + ' ' + (newQ.length === 1 ? 'is' : 'are') + ' new since the previous close' : ''}.`);
  const p2 = el('p', 'idxline');
  const ix = (DATA.indices || []).slice(0, 2).filter(i => i.r1 != null);
  const {med, far, n: nIdx} = mktFacts(all, dips);
  if (ix.length) {
    p2.append('Index moves at the latest close: ');
    ix.forEach((i, k) => { if (k) p2.append(', '); p2.append(i.name + ' '); p2.append(el('span', 'num ' + sgnCls(i.r1), pct(i.r1))); });
    p2.append(' (1 day). ');
  }
  if (med != null) { p2.append('The median screened stock moved '); p2.append(el('span', 'num ' + sgnCls(med), pct(med))); p2.append(' over 5 days. '); }
  if (nIdx) p2.append(`${far} of ${nIdx} flagged dips fell at least 5 points more than their own index.`);
  box.append(h, p1);
  if (p2.childNodes.length) box.append(p2);
}

