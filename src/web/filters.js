// ---------- active filters: removable chips and a reset ----------
const DEF_Q = ST.quality.min_score;
function syncSegs() { ['show', 'region'].forEach(id => document.querySelectorAll('#' + id + ' button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === S[id])))); }
const CLEAR = {
  show: () => { S.show = 'dips'; syncSegs(); }, region: () => { S.region = ''; syncSegs(); }, q: () => { $('q').value = ''; },
  knife: () => { $('hideknife').checked = false; }, qmin: () => { $('qmin').value = DEF_Q; },
  win: () => { $('win').value = 'any'; $('drop').value = Math.round(WIN.any.def * 100); },
};
function activeList() {
  const a = [], q = $('q').value.trim();
  if (S.show !== 'dips') a.push(['show', 'Showing: ' + (S.show === 'all' ? 'All stocks' : 'Dips meeting the check thresholds')]);
  if (S.region) a.push(['region', 'Region: ' + S.region]);
  if (q) a.push(['q', 'Search: “' + q + '”']);
  if ($('hideknife').checked) a.push(['knife', 'Falling knives hidden']);
  if (+$('qmin').value !== DEF_Q) a.push(['qmin', 'Quality score ≥ ' + $('qmin').value]);
  if ($('win').value !== 'any') a.push(['win', WIN[$('win').value].label + ' ≥ ' + $('drop').value + '% drop']);
  return a;
}
function activeChips() {
  const bar = $('activebar'), a = activeList(); bar.replaceChildren(); bar.hidden = !a.length;
  a.forEach(([k, label]) => {
    const b = el('button', 'fchip', label); b.type = 'button'; b.append(el('span', 'x', '×')); b.setAttribute('aria-label', 'Remove filter: ' + label);
    b.onclick = () => { CLEAR[k](); S.sortKey = null; S.focus = '#head th'; render(); }; bar.append(b);
  });
  if (a.length > 1) { const r = el('button', 'resetbtn', 'Reset all'); r.type = 'button'; r.onclick = resetAll; bar.append(r); }
}
function resetAll() { Object.values(CLEAR).forEach(f => f()); S.sortKey = null; S.focus = '#head th'; render(); }

