/* Everything filters the already rendered snapshot. No requests or ticket holds. */
(() => {
  const form = document.getElementById('powerFilters');
  const body = document.getElementById('boardRows');
  const rows = Array.from(body.querySelectorAll('.showing'));
  const search = document.getElementById('searchInput');
  const date = document.getElementById('dateFilter');
  const room = document.getElementById('roomFilter');
  const mode = document.getElementById('modeFilter');
  const sort = document.getElementById('sortField');
  let preset = 'all';
  const number = (row, key) => row.dataset[key] === '' ? null : Number(row.dataset[key]);
  const format = value => value === null ? '—' : value.toLocaleString('en-US');
  const set = (id, value) => { document.getElementById(id).textContent = value; };
  // Calendar comparisons always use Durham's date, even for visitors overseas.
  const todayParts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(new Date());
  const part = key => todayParts.find(p => p.type === key).value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  const todayUTC = Date.parse(today + 'T00:00:00Z');

  function apply() {
    const query = search.value.trim().toLocaleLowerCase();
    const visible = rows.filter(row => {
      const day = row.dataset.starts.slice(0, 10);
      const dayOffset = (Date.parse(day + 'T00:00:00Z') - todayUTC) / 86400000;
      const matchesDate = date.value === 'all' ||
        (date.value === 'today' ? day === today :
          date.value === 'week' ? dayOffset >= 0 && dayOffset < 7 : day === date.value);
      const full = number(row, 'filled');
      const matchesPreset = preset === 'all' || (full !== null &&
        (preset === 'quiet' ? full < 50 && row.dataset.onSale === 'true' : full >= 70));
      const matches = matchesDate && matchesPreset &&
        (room.value === 'all' || row.dataset.venue === room.value) &&
        (mode.value === 'all' || row.dataset.mode === mode.value) &&
        `${row.dataset.title} ${row.dataset.venue}`.toLocaleLowerCase().includes(query);
      row.hidden = !matches;
      return matches;
    });
    const field = sort.value;
    rows.sort((a, b) => {
      if (field === 'starts') return a.dataset.starts.localeCompare(b.dataset.starts);
      const av = number(a, field), bv = number(b, field);
      // Unknown values always sort last, including genuine negative sales deltas.
      if (av === null || bv === null) return av === bv ? 0 : av === null ? 1 : -1;
      const order = ['left', 'price'].includes(field) ? av - bv : bv - av;
      return order || a.dataset.starts.localeCompare(b.dataset.starts);
    }).forEach(row => body.appendChild(row));

    document.querySelectorAll('[data-preset]').forEach(b => b.setAttribute('aria-pressed', b.dataset.preset === preset));
    document.querySelectorAll('.day-signal').forEach(b => b.setAttribute('aria-pressed', b.dataset.date === date.value));
    set('boardNote', `${visible.length} of ${rows.length} showings`);
    document.getElementById('powerEmpty').hidden = visible.length > 0;
    const sales = visible.filter(r => number(r, 'total') > 0 && number(r, 'sold') !== null);
    const available = visible.filter(r => number(r, 'left') !== null);
    const sold = sales.reduce((sum, r) => sum + number(r, 'sold'), 0);
    const total = sales.reduce((sum, r) => sum + number(r, 'total'), 0);
    const left = available.reduce((sum, r) => sum + number(r, 'left'), 0);
    const pct = total ? Math.round(sold / total * 1000) / 10 : null;
    set('metricShowings', format(visible.length));
    set('metricScope', visible.length === rows.length ? 'All upcoming showings' : 'Matching your filters');
    set('metricSold', format(sales.length ? sold : null));
    set('metricLeft', format(available.length ? left : null));
    set('metricPercent', pct === null ? '—' : `${pct}%`);
    set('coverage', `${sales.length} of ${visible.length} showings have sales data`);
    // Preserve accessible meter semantics when moving between known and unknown data.
    const meter = document.querySelector('#summaryMeter .meter-track');
    const fill = meter.querySelector('.meter-fill') || document.createElement('span');
    fill.className = 'meter-fill';
    fill.style.width = `${Math.max(0, Math.min(100, pct || 0))}%`;
    fill.dataset.positive = pct > 0;
    meter.appendChild(fill);
    meter.parentElement.classList.toggle('is-unknown', pct === null);
    if (pct === null) {
      ['role', 'aria-valuenow', 'aria-valuetext', 'aria-valuemin', 'aria-valuemax'].forEach(a => meter.removeAttribute(a));
    } else {
      Object.entries({role: 'meter', 'aria-label': 'Seats sold', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': Math.max(0, Math.min(100, pct)), 'aria-valuetext': `${pct}% of known capacity sold`}).forEach(([k,v]) => meter.setAttribute(k,v));
    }
    document.querySelector('#summaryMeter .meter-label').textContent = pct === null ? 'No inventory' : `${pct}% full`;
  }
  form.addEventListener('submit', e => e.preventDefault());
  form.addEventListener('input', apply);
  form.addEventListener('change', apply);
  form.addEventListener('reset', () => { preset = 'all'; setTimeout(apply, 0); });
  document.getElementById('emptyReset').addEventListener('click', () => form.reset());
  document.querySelectorAll('[data-preset]').forEach(button => button.addEventListener('click', () => { preset = button.dataset.preset; apply(); }));
  document.querySelectorAll('.day-signal').forEach(button => button.addEventListener('click', () => {
    date.value = date.value === button.dataset.date ? 'all' : button.dataset.date;
    apply();
  }));
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !e.metaKey && !e.ctrlKey && !e.altKey && !['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)) {
      e.preventDefault(); search.focus();
    }
  });
  apply();
})();
