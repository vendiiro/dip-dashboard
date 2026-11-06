// ---------- trigger alerts ----------
let alertsOpen = false;
function alertsPanel() {
  const box = $('alerts'), list = DATA.alerts || [];
  box.replaceChildren(); box.className = 'alerts';
  if (DATA.alerts === undefined) { box.hidden = true; return; }
  box.hidden = false;
  if (DATA.alerts === null) {          // the alert step failed: say so, never show it as a quiet day
    box.classList.add('alerts-empty', 'unavail'); const h0 = el('h2', null, '⚠ Trigger alerts · unavailable'); h0.id = 'alerts-h';
    box.append(h0, el('p', 'sub', 'Alerts could not be evaluated for this run (see output/run.log). This is not the same as no alerts.')); return;
  }
  const h = el('h2', null, 'Trigger alerts · ' + (list.length || 'none at the latest close')); h.id = 'alerts-h';
  if (!list.length) { box.classList.add('alerts-empty'); box.append(h, el('p', 'sub', 'No research conditions changed state at the latest close. Informational only, not advice.')); return; }
  box.classList.remove('alerts-empty');
  box.append(h, el('p', 'sub', 'Research conditions that became true at the latest close. Informational only, not advice.'));
  const CAP = window.matchMedia('(max-width:480px)').matches ? 3 : 5, ul = el('ul');
  (alertsOpen ? list : list.slice(0, CAP)).forEach(a => {
    const li = el('li'); li.append(el('span', 'k ' + (a.kind === 'caution' ? 'caution' : 'info'), a.kind === 'caution' ? 'Caution' : 'Info'), el('span', null, a.headline || ''));
    const c = a.context || {}, bits = [];
    if (c.r5 != null) bits.push('5d ' + pct(c.r5));
    if (c.q != null) bits.push('quality score ' + c.q);
    if (a.detail || bits.length) li.append(el('span', 'd', [a.detail, bits.join(' · ')].filter(Boolean).join(' — ')));
    if (c.setup && c.setup_text) {                       // keyed on the enum, worded from setup_text
      const cls = {'Quality dip': 'b-good', 'Falling knife': 'b-crit', 'Dip, low quality': 'b-plain', 'Dip, no fundamentals': 'b-warn', 'No dip': 'b-none'}[c.setup] || 'b-none';
      const sb = el('span', 'd'); sb.append(el('span', 'badge ' + cls, c.setup_text)); li.append(sb);
    }
    ul.append(li);
  });
  box.append(ul);
  if (list.length > CAP) { const b = el('button', 'alerts-more', alertsOpen ? 'Show fewer' : 'Show all ' + list.length + ' alerts'); b.type = 'button'; b.setAttribute('aria-expanded', String(alertsOpen)); b.setAttribute('aria-controls', 'alerts'); b.onclick = () => { alertsOpen = !alertsOpen; alertsPanel(); const nb = $('alerts').querySelector('.alerts-more'); if (nb) nb.focus(); }; box.append(b); }
}

