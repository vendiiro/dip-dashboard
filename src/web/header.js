// ---------- header, data quality ----------
const latest = a => a.length ? a.map(r => r.asof).sort().at(-1) : null;
$('m-us').textContent = fmtDay(latest(rows.filter(r => r.region === 'US')));
$('m-eu').textContent = fmtDay(latest(rows.filter(r => r.region !== 'US')));
$('m-gen').textContent = DATA.generated + (DATA.tz ? ' ' + DATA.tz.split('/').pop() : '');
$('demo').hidden = !DATA.demo;

// ---------- stale data: the newest prices are more than STALE_WEEKDAYS weekdays older than today (this browser's clock) ----------
// Weekdays, not trading days: a public holiday can raise a false alarm, so the text names the date and says "may".
// Only the newest bar of any stock counts (US and Europe normally differ by a day). Skipped for the synthetic demo.
const STALE_WEEKDAYS = 2;
function weekdaysAfter(isoFrom, to) {            // Mon-Fri days d with from < d <= to (to: a local Date)
  const d = new Date(isoFrom + 'T12:00:00'), end = new Date(to.getFullYear(), to.getMonth(), to.getDate(), 12);
  let n = 0; for (d.setDate(d.getDate() + 1); d <= end; d.setDate(d.getDate() + 1)) if (d.getDay() % 6) n++;
  return n;
}
guard('the stale-data check', () => {
  const newest = latest(rows), box = $('stale');
  if (DATA.demo || !newest) { box.hidden = true; return; }
  const n = weekdaysAfter(newest, new Date());
  box.hidden = n <= STALE_WEEKDAYS; if (box.hidden) return;
  const ic = el('span', 'ic', '!'); ic.setAttribute('aria-hidden', 'true');
  const p = el('p'); p.append(el('b', null, `Newest prices are from ${fmtDay(newest)}, ${n} weekdays ago. `),
    'The nightly run may have failed, or this is an older copy of the page. These are screen results for that day, not today.');
  box.replaceChildren(ic, p); box.dataset.weekdays = String(n);
});

guard('the data-quality badge', function dataQuality() {
  const iss = DATA.issues || [];
  const errs = iss.filter(i => i.severity === 'error'), warns = iss.filter(i => i.severity === 'warn');
  const skipped = DATA.data_quality || [];
  const checks = iss.filter(i => i.check === 'crosscheck_ok' || i.check === 'crosscheck_diff');
  const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
  // A ticker the source simply did not return is shown as "without price data" (a warning), not as a red error: the run itself is fine.
  const hardErrs = errs.filter(i => i.check !== 'no_data');
  const state = hardErrs.length ? 'crit' : (errs.length || warns.length) ? 'warn' : 'ok';
  $('dqbtn').className = 'dq s-' + state;
  $('dqic').textContent = state === 'ok' ? '✓' : state === 'warn' ? '!' : '✕';
  const partial = warns.filter(i => i.check === 'partial_bar').length;
  const otherNotes = hardErrs.length + warns.length - partial;
  const parts = [rows.length + ' screened'];
  if (skipped.length) parts.push(skipped.length + ' without price data');
  if (partial) parts.push(partial + ' intraday');
  if (otherNotes) parts.push(plural(otherNotes, 'other note'));
  $('dqlabel').textContent = (state === 'ok' ? 'Data checks passed · ' : '') + parts.join(' · ');
  $('dqbtn').title = 'Left out: the price source returned no usable data for that ticker. Intraday: the latest bar is dated today, so the session may still be open. Click for details.';
  const p = $('dqpanel');
  p.append(el('b', null, 'Data quality for this run'));
  p.append(el('div', null, `${rows.length} of ${rows.length + (DATA.data_quality || []).length} tickers screened. Stocks with an error are left out of the table.`));
  const list = (title, items) => {
    if (!items.length) return;
    p.append(el('div', 'muted', title));
    const ul = el('ul');
    const byCheck = {}; items.forEach(i => (byCheck[i.check] = byCheck[i.check] || []).push(i));
    Object.entries(byCheck).forEach(([check, group]) => {
      const name = check.replaceAll('_', ' ');
      if (group.length <= 3) { group.forEach(i => { const li = el('li'); li.append(el('span', 't', i.ticker + ' '), document.createTextNode(name + ': ' + i.detail)); ul.append(li); }); return; }
      const details = [...new Set(group.map(i => i.detail))];     // many stocks with the same finding: one line
      const li = el('li'); li.append(el('span', 't', group.map(i => i.ticker).join(', ') + ' '), document.createTextNode('(' + group.length + ' stocks) ' + name + ': ' + (details.length === 1 ? details[0] : 'details are in data_quality.csv')));
      ul.append(li);
    });
    p.append(ul);
  };
  list('Errors', errs); list('Warnings', warns);
  if (skipped.length) {
    p.append(el('div', 'muted', 'Left out of the table'));
    const ul = el('ul'); skipped.forEach(i => { const li = el('li'); li.append(el('span', 't', i.t + ' '), document.createTextNode(String(i.reason).replaceAll('_', ' ') + ': ' + i.detail)); ul.append(li); }); p.append(ul);
  }
  if (checks.length) {
    const bad = checks.filter(c => c.check === 'crosscheck_diff').length;
    p.append(el('div', 'muted', `Cross-check: ${checks.length} random tickers compared with an independent exchange source (Nasdaq or Nasdaq Nordic); ${bad ? bad + ' differ by more than 1%.' : 'all closes agree within 1%.'}`));
    const ul = el('ul'); checks.forEach(i => { const li = el('li'); li.append(el('span', 't', i.ticker + ' '), document.createTextNode(i.detail)); ul.append(li); }); p.append(ul);
  } else p.append(el('div', 'muted', 'No cross-check against a second source was run.'));
  const fx = Object.entries(DATA.fx_to_usd || {});
  if (fx.length) p.append(el('div', 'muted', 'Market cap is compared in USD. Rates (USD per unit): ' + fx.map(([c, r]) => c + ' ' + r.toFixed(4)).join(' · ') + '.'));
  $('dqbtn').onclick = () => { p.hidden = !p.hidden; $('dqbtn').setAttribute('aria-expanded', String(!p.hidden)); };
  dqBase = {label: parts.join(' · ')};         // without 'Data checks passed', which a drawing failure contradicts
  showFails();                                 // a failure noted before this point still reaches the badge
});

