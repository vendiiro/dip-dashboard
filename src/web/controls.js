// ---------- controls ----------
const segs = (id, key) => document.querySelectorAll('#' + id + ' button').forEach(b => b.onclick = () => { document.querySelectorAll('#' + id + ' button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); S[key] = b.dataset.v; S.sortKey = null; render(); });
document.querySelectorAll('#show button, #region button').forEach(b => b.dataset.label = b.textContent);
segs('show', 'show'); segs('region', 'region');
$('resetbtn').onclick = resetAll;
['drop', 'qmin', 'hideknife', 'q'].forEach(id => $(id).addEventListener('input', () => { S.sortKey = null; render(); }));
$('win').addEventListener('change', () => { $('drop').value = Math.round(WIN[$('win').value].def * 100); S.sortKey = null; render(); });
$('colbtn').onclick = () => { S.more = !S.more; render(); $('colbtn').focus(); };
