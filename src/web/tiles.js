// ---------- filters toggle (phone) ----------
function ctlSummary() {
  const pressed = id => { const b = document.querySelector('#' + id + ' [aria-pressed="true"]'); return b ? (b.dataset.label || b.textContent).trim() : ''; };
  $('ctlsum').textContent = [pressed('show'), pressed('region'), 'Quality score ≥ ' + $('qmin').value].filter(Boolean).join(' · ');
}
$('ctltoggle').addEventListener('click', () => {
  const open = $('controls').classList.toggle('open'); $('ctltoggle').setAttribute('aria-expanded', String(open));
});

// ---------- tiles ----------
function tiles(all) {
  const box = $('tiles'); box.replaceChildren();
  const dipsN = all.filter(r => vw(r).rank > 0).length, qd = all.filter(r => vw(r).rank === 4), kn = all.filter(r => vw(r).label === 'Falling knife');
  const newQ = qd.filter(r => wasQualityDip(r) === false);
  const mk = (id, lab, n, foot, chips) => {
    const t = el('div', 'tile'); t.dataset.testid = id; t.append(el('div', 'lab', lab), el('div', 'big', String(n)));
    if (chips && chips.length) {
      const c = el('div', 'chips'), CAP = window.matchMedia('(max-width:480px)').matches ? 5 : 8; let open = false;
      const draw = () => {
        c.replaceChildren(); (open ? chips : chips.slice(0, CAP)).forEach(x => { const s = el('span', 'chip', x); s.dataset.testid = 'tile-chip'; c.append(s); });
        if (chips.length > CAP) { const b = el('button', 'chipmore', open ? 'show fewer' : '+' + (chips.length - CAP) + ' more'); b.type = 'button'; b.dataset.testid = 'tile-chip-more'; b.setAttribute('aria-expanded', String(open)); b.onclick = () => { open = !open; draw(); const nb = c.querySelector('.chipmore'); if (nb) nb.focus(); }; c.append(b); }
      };
      draw(); t.append(c);
    }
    if (foot) t.append(el('div', 'foot', foot)); box.append(t);
  };
  mk('tile-quality', 'Dips meeting the check thresholds', qd.length, `${qd.length} of ${dipsN} dips have quality score ≥ ${$('qmin').value} and net margin above 0 · drop window: ${$('win').value === 'any' ? 'default' : 'chosen window'}`, qd.map(r => r.t));
  mk('tile-new', 'New since the previous close', newQ.length, newQ.length ? 'Started meeting the check thresholds with the latest close' : 'Same dips meeting the check thresholds as the previous close', newQ.map(r => r.t));
  mk('tile-knife', 'Falling-knife flags', kn.length, 'Dipping inside a long downtrend', kn.map(r => r.t));
  const t = el('div', 'tile'); t.dataset.testid = 'tile-market'; t.append(el('div', 'lab', 'Market context'));
  if (DATA.indices && DATA.indices.length) {
    const g = el('div', 'mkt'); g.append(el('span', 'h', 'Index'), el('span', 'h num', '1d'), el('span', 'h num', '5d'));
    const head = DATA.indices.slice(0, 3);   // the payload lists the main regional indices first
    let open = false;
    const draw = () => {
      g.replaceChildren(el('span', 'h', 'Index'), el('span', 'h num', '1d'), el('span', 'h num', '5d'));
      (open ? DATA.indices : head).forEach(ix => g.append(el('span', null, ix.name), el('span', 'num ' + sgnCls(ix.r1), pct(ix.r1)), el('span', 'num ' + sgnCls(ix.r5), pct(ix.r5))));
    };
    draw(); t.append(g);
    if (DATA.indices.length > head.length) {
      const b = el('button', 'mktmore'); b.type = 'button';
      const label = () => open ? 'Show main indices only' : 'Show all ' + DATA.indices.length + ' indices';
      b.textContent = label(); b.title = 'The country indices are the ones each stock is compared with in “5d vs index”.'; b.setAttribute('aria-expanded', 'false');
      b.onclick = () => { open = !open; draw(); b.textContent = label(); b.setAttribute('aria-expanded', String(open)); };
      t.append(b);
    }
    t.append(el('div', 'foot', 'A broad selloff lifts every stock’s drop. Compare with “5d vs index”.'));
    const mf = mktFacts(all, all.filter(r => vw(r).rank > 0)), bits = [];
    if (mf.med != null) bits.push(`Median stock ${pct(mf.med)} (5d)`);
    if (mf.n) bits.push(`${mf.far} of ${mf.n} dips fell 5+ points more than their index`);
    if (bits.length) { const ml = el('div', 'mktline', bits.join(' · ')); ml.dataset.testid = 'tile-market-line'; t.append(ml); }
  } else t.append(el('div', 'foot', 'Index data was not available for this run, so market-wide moves cannot be separated from stock-specific ones.'));
  box.append(t);
}

