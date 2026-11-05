// ---------- footer definitions from the settings actually used ----------
guard('the footer definitions', () => {
$('def-dip').textContent = `Fell at least the minimum drop over the chosen window. Defaults: 1 day ≤ ${MINUS}${(ST.dip.drop_1d * 100).toFixed(0)}%, 5 days ≤ ${MINUS}${(ST.dip.drop_5d * 100).toFixed(0)}%, or ≥ ${(ST.dip.drawdown_20d * 100).toFixed(0)}% below the 20-day high. Untested defaults.`;
$('def-q').textContent = `Share of the checks that apply and have data (six in total) that passed: ROE (return on equity) ≥ ${(ST.quality.roe_min * 100).toFixed(0)}%, net margin ≥ ${(ST.quality.margin_min * 100).toFixed(0)}%, debt/equity (debt divided by shareholders’ equity) ≤ ${ST.quality.debt_to_equity_max}%, positive free cash flow, positive revenue growth, market cap ≥ ${(ST.quality.market_cap_min / 1e9).toFixed(0)}B USD. Needs at least three checks with data; each stock shows how many it was scored on. Banks and insurers skip the debt and free-cash-flow checks, and utilities and real-estate companies use a debt/equity limit of 300%. Free fundamentals can be stale or wrong. Dips meeting the check thresholds: dips with a quality score at or above the minimum and net margin above 0.`;
$('def-knife').textContent = `Price below a ${ST.knife.below_200d_falling ? 'falling ' : ''}200-day average and at least ${(ST.knife.drawdown_52w * 100).toFixed(0)}% under the 52-week high. A long slide, not a one-off drop.`;
$('def-src').textContent = DATA.demo ? 'Synthetic demo data.' : 'Daily adjusted prices and fundamentals from Yahoo Finance via yfinance. Random tickers are cross-checked against Nasdaq and Nasdaq Nordic through OpenBB (see the data-quality badge). Fundamentals are cached for 7 days.';
});

// ---------- definitions toggle: links to #def-... open it first ----------
const defs = $('defs');
function openDef(id) {
  const t = id && document.getElementById(id); if (!t || !defs.contains(t)) return false;
  defs.open = true;
  document.querySelectorAll('footer .hit').forEach(x => x.classList.remove('hit')); t.classList.add('hit');
  const h = t.previousElementSibling && t.previousElementSibling.tagName === 'DT' ? t.previousElementSibling : null;   // the term heading
  if (h) h.classList.add('hit');
  (h || t).scrollIntoView({block: 'start'});
  t.tabIndex = -1; t.focus({preventScroll: true}); return true;
}
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('a[href^="#def-"]'); if (!a) return;
  if (openDef(a.getAttribute('href').slice(1))) { e.preventDefault(); history.replaceState(null, '', a.getAttribute('href')); }
});
window.addEventListener('hashchange', () => openDef(location.hash.slice(1)));
if (location.hash) openDef(location.hash.slice(1));
