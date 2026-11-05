// ---------- setup label under the current controls ----------
// The key (`label`) stays the stable enum the nightly screen uses; the words a reader sees come from `text` (setup_text in the payload).
const SETUP_TIP = {
  'Quality dip': 'Dip, more checks passed. Fell past the drop rule; quality score is at or above the minimum (net margin above 0). A candidate to research, not a signal. The checks are definitions, not tested filters.',
  'Falling knife': 'Dipping inside a long downtrend: below a falling 200-day average and far under the 52-week high.',
  'Dip, low quality': 'Dip, fewer checks passed. Fell past the drop rule; fewer checks passed than the minimum score, or net margin is 0 or below. This describes check results, not the company.',
  'Dip, no fundamentals': 'Fell past the drop rule, but the fundamentals are missing or too thin to score, so no score-based label is shown.',
  'Distorted': 'Fell past the drop rule, but the fundamentals look unreliable (see Evidence), so no score-based label is shown.',
  'No dip': 'Has not fallen past the drop rule.',
};
function setupOf(r, m) {
  const w = $('win').value, drop = -(+$('drop').value) / 100, v = m[w];
  const isDip = w === 'any' ? !!m.dip : (v != null && v <= drop);    // 'any' = the rules in settings.toml (1d, 5d or 20d high)
  const mk = (label, rank, cls, icon) => ({label, rank, cls, icon, text: setupText(label, r)});
  if (!isDip) return mk('No dip', 0, 'b-none', '·');
  if (m.knife) return mk('Falling knife', 1, 'b-crit', '⚠');
  if (r.q == null) return mk('Dip, no fundamentals', 2, 'b-warn', '?');
  if (r.q_status === 'distorted') return mk('Dip, no fundamentals', 2, 'b-warn', '?');   // same order as screen.setup_label
  if ((r.q_must_failed || []).length) return mk('Dip, low quality', 2, 'b-serious', '✗');
  if (r.q >= +$('qmin').value) return mk('Quality dip', 4, 'b-good', '✓');
  return mk('Dip, low quality', 2, 'b-serious', '✗');
}
// Reader-facing text. At the nightly label the payload's own setup_text is used; under other controls the same wording is built here.
function setupText(label, r) {
  if (r.setup === label && r.setup_text) return r.setup_text;                    // the nightly label: the payload's own words
  if (label === 'Dip, no fundamentals') return r.q_status === 'distorted' ? 'Dip · data looks unreliable' : 'Dip, no fundamentals';
  if (label === 'Quality dip' || label === 'Dip, low quality') {
    if (r.q_scored === 0) return 'Dip, no fundamentals';
    if (r.q_passed == null || r.q_scored == null) return 'Dip';
    const k = r.q_applicable != null ? r.q_applicable - r.q_scored : 0;
    return `Dip · passes ${r.q_passed} of ${r.q_scored} scored checks` + (k > 0 ? ` (${k} no data)` : '');
  }
  return label;
}
// One sentence on the evidence behind the checks: how many had data, and why a score may not be readable.
function evidenceNote(r) {
  const bits = [];
  if (r.q_scored != null && r.q_applicable != null) bits.push(`scored on ${r.q_scored}/${r.q_applicable}`);
  if (r.q_status === 'distorted') bits.push('distorted' + (r.q_why ? ': ' + r.q_why : ''));
  else if (r.q_status === 'thin') bits.push('fewer checks had data than apply');
  else if (r.q_status === 'no_data') bits.push('too few checks had data');
  if ((r.q_must_failed || []).length) bits.push('net margin is not above 0');
  if ((r.q_must_missing || []).length) bits.push('net margin missing (listed as missing, not failed)');
  return bits.join(' · ');
}
const wasQualityDip = r => r.prev ? setupOf(r, r.prev).rank === 4 : null;   // null = no history to say
// The label under the current controls lives in this Map, not on the row: the payload's own `r.setup` (the nightly screen's
// label at the default settings, a string) stays untouched, so a debugger or a test sees both.
const VIEW = new Map(), vw = r => VIEW.get(r);
window.__dipView = t => { const r = rows.find(x => x.t === t); return r && VIEW.get(r) ? {...VIEW.get(r)} : null; };
function badge(r) {
  const v = vw(r), bd = el('span', 'badge ' + v.cls, v.icon + ' ' + v.text), ev = evidenceNote(r);
  bd.title = SETUP_TIP[r.q_status === 'distorted' && v.label === 'Dip, no fundamentals' ? 'Distorted' : v.label] + (ev && v.rank > 0 ? ' Evidence: ' + ev + '.' : '');
  return bd;
}

