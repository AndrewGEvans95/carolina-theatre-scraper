/* Use the canonical ISO showtime for dates; Firefox needn't parse display labels. */
const scheduleControl = id => document.getElementById(id);
const theatreDay = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit'
}).formatToParts(new Date());
const theatrePart = key => theatreDay.find(p => p.type === key).value;
const todayUTC = Date.parse(`${theatrePart('year')}-${theatrePart('month')}-${theatrePart('day')}T00:00:00Z`);

function filterByDay() {
  const group = scheduleControl('groupFilter').value;
  const day = scheduleControl('dayFilter').value;
  const venue = scheduleControl('venueFilter').value;
  const capacity = scheduleControl('capacityFilter').value;
  let count = 0;
  document.querySelectorAll('.day, .movie-group').forEach(section => {
    const active = section.classList.contains(group === 'by-day' ? 'day' : 'movie-group');
    let sectionCount = 0;
    section.querySelectorAll('.movie').forEach(movie => {
      const offset = (Date.parse(movie.dataset.formattedDatetime.slice(0, 10) + 'T00:00:00Z') - todayUTC) / 86400000;
      const inDate = day === 'all' || (day === 'week' ? offset >= 0 && offset < 7 :
        day === 'month' ? offset >= 0 && offset < 31 : movie.dataset.movieDate === day);
      const full = movie.hasAttribute('data-full') ? Number(movie.dataset.full) : null;
      const inCapacity = capacity === 'all' || (full !== null && (
        capacity === 'quiet' ? full < 50 : capacity === 'busy' ? full >= 50 : full >= 90));
      const visible = active && inDate && inCapacity && (venue === 'all' || movie.dataset.movieCinema === venue);
      movie.classList.toggle('hidden', !visible);
      if (visible) sectionCount++;
    });
    section.classList.toggle('hidden', !sectionCount);
    count += sectionCount;
  });
  scheduleControl('scheduleCount').textContent = `${count} showtime${count === 1 ? '' : 's'}`;
  scheduleControl('scheduleEmpty').hidden = count > 0;
}

function resetSchedule() {
  scheduleControl('dayFilter').value = 'all';
  scheduleControl('venueFilter').value = 'all';
  scheduleControl('capacityFilter').value = 'all';
  filterByDay();
}

function revealShowtime(id) {
  const target = document.getElementById(id);
  if (!target || !target.classList.contains('movie')) return;
  scheduleControl('groupFilter').value = target.closest('.day') ? 'by-day' : 'by-movie';
  resetSchedule();
  target.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center'});
  target.classList.add('highlight');
  setTimeout(() => target.classList.remove('highlight'), 2500);
}

let dialogTrigger = null;
function showOtherTimes(id) {
  const row = document.getElementById(id);
  if (!row) return;
  dialogTrigger = document.activeElement;
  const dialog = scheduleControl('otherTimesDialog');
  const list = dialog.querySelector('.other-times-list');
  list.replaceChildren();
  const seen = new Set();
  document.querySelectorAll('.day .movie').forEach(other => {
    const key = `${other.dataset.formattedDatetime}|${other.dataset.movieCinema}`;
    if (other.dataset.movieTitle !== row.dataset.movieTitle || seen.has(key) ||
        (other.dataset.formattedDatetime === row.dataset.formattedDatetime && other.dataset.movieCinema === row.dataset.movieCinema)) return;
    seen.add(key);
    const link = document.createElement('a');
    link.className = 'other-times-link';
    link.href = '#' + other.id;
    link.textContent = `${other.dataset.movieDate} · ${other.dataset.movieTime} · ${other.dataset.movieCinema}`;
    link.addEventListener('click', () => closeOtherTimesDialog(other.id));
    list.appendChild(link);
  });
  if (!list.children.length) list.textContent = 'No other showtimes for this film.';
  scheduleControl('otherTimesTitle').textContent = row.dataset.movieTitle;
  dialog.classList.remove('hidden');
  scheduleControl('dialogOverlay').classList.remove('hidden');
  document.body.classList.add('modal-open');
  (list.querySelector('a') || dialog.querySelector('button')).focus();
}

function closeOtherTimesDialog(id) {
  scheduleControl('otherTimesDialog').classList.add('hidden');
  scheduleControl('dialogOverlay').classList.add('hidden');
  document.body.classList.remove('modal-open');
  if (dialogTrigger) dialogTrigger.focus();
  if (id) revealShowtime(id);
}

async function copyShareLink(id, event) {
  const button = event.currentTarget;
  const url = new URL(window.location.href);
  url.hash = id;
  try {
    await navigator.clipboard.writeText(url.href);
    button.classList.add('copied');
    button.setAttribute('aria-label', 'Link copied');
    setTimeout(() => {button.classList.remove('copied'); button.setAttribute('aria-label', 'Copy link to this showtime');}, 2000);
  } catch (_) {
    // A real selectable link also works when clipboard permission is denied.
    window.prompt('Copy this showtime link:', url.href);
  }
}

document.addEventListener('keydown', e => {
  const dialog = scheduleControl('otherTimesDialog');
  if (dialog.classList.contains('hidden')) return;
  if (e.key === 'Escape') closeOtherTimesDialog();
  if (e.key === 'Tab') {
    const focusable = Array.from(dialog.querySelectorAll('a, button'));
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {e.preventDefault(); last.focus();}
    else if (!e.shiftKey && document.activeElement === last) {e.preventDefault(); first.focus();}
  }
});
window.addEventListener('hashchange', () => revealShowtime(location.hash.slice(1)));
filterByDay();
if (location.hash) revealShowtime(location.hash.slice(1));
