(() => {
const $ = id => document.getElementById(id);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };

// ---------- drawing failures: shown on the page, never a silent blank ----------
// Each section draws inside its own guard, and each table row and phone card inside its own, so one bad value leaves the rest
// of the page readable. Every failure is listed in the red box at the top, logged with console.error, and turns the
// data-quality badge red.
const FAILS = new Map();                      // key -> {part, t, msg}; keyed so a redraw does not list the same failure twice
let dqBase = null;                            // the badge as the data checks left it, before drawing failures are added
function noteFail(part, t, err) {
  const msg = String(err && err.message || err).slice(0, 160), key = part + '|' + (t || '');
  if (!FAILS.has(key)) console.error('dashboard: could not draw ' + part + (t ? ' for ' + t : '') + ':', err);
  FAILS.set(key, {part, t, msg});
  showFails();
}
function showFails() {
  const box = $('fail'); if (!box || !FAILS.size) return;
  const list = [...FAILS.values()], tks = list.filter(f => f.t).map(f => f.t);
  box.replaceChildren(el('span', 'ic', '!'));
  box.firstChild.setAttribute('aria-hidden', 'true');
  const p = el('p'); p.append(el('b', null, 'This page could not draw part of the screen' + (tks.length ? ' (' + [...new Set(tks)].join(', ') + ')' : '') + '. '),
    'The data file may be damaged; see the data-quality note.' + (FAILS.has('the page|') ? '' : ' The rest of the page is drawn as usual.'));
  const ul = el('ul');
  list.forEach(f => { const li = el('li'); if (f.t) li.append(el('span', 't', f.t), ' · '); li.append(f.part + ': ' + f.msg); ul.append(li); });
  box.append(p, ul); box.hidden = false;
  const b = $('dqbtn');
  if (b && dqBase) {
    b.className = 'dq s-crit'; $('dqic').textContent = '✕';
    const nSt = new Set(tks).size, nOther = list.filter(f => !f.t).length;   // one stock counts once, however many parts of it failed
    const bits = []; if (nSt) bits.push(nSt + ' stock' + (nSt === 1 ? '' : 's')); if (nOther) bits.push(nOther + ' part' + (nOther === 1 ? '' : 's'));
    $('dqlabel').textContent = dqBase.label + ' · ' + bits.join(', ') + ' failed to draw';
  }
}
function guard(part, fn, t) { try { return fn(); } catch (e) { noteFail(part, t, e); return undefined; } }
window.__dipFails = FAILS;                    // read by the fallback script below and by the browser tests

