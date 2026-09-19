"""Browser regression checks. Requires Playwright (development only).

python scripts/check_ui.py --url http://127.0.0.1:8000 --output /tmp/ui-check
Also accepts a file:/// URL for a generated directory, or the live site.
"""

import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright


def assert_layout(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page overflows horizontally'
    assert '{{' not in page.locator('body').inner_text(), 'Unresolved template placeholder'
    broken = page.evaluate('''() => [...document.querySelectorAll('.meter-track')]
      .filter(e => e.getBoundingClientRect().width > 0).flatMap(e => {
        const r = e.getBoundingClientRect(), fill = e.querySelector('.meter-fill');
        const f = fill && fill.getBoundingClientRect();
        const percent = Number(e.getAttribute('aria-valuenow'));
        return r.width < 40 || r.height < 8 || (percent > 0 && (!f || f.width < 1 || f.height < 5)) ||
          (f && f.width > r.width + 1) ? [{width:r.width, height:r.height, percent}] : [];
      })''')
    assert not broken, f'Invisible/collapsed meters: {broken}'
    assert page.locator('h1').count() == 1


def check_power(page):
    rows = page.locator('.showing:visible')
    initial = rows.count()
    assert initial, 'Need a populated snapshot to test interactions'
    first = rows.first
    first.locator('summary').focus()
    page.keyboard.press('Enter')
    assert first.get_attribute('open') is not None
    assert first.locator('.showing-details').is_visible()
    assert_layout(page)
    page.keyboard.press('Enter')
    page.locator('#searchInput').fill('no-such-film-983726')
    assert rows.count() == 0
    assert page.locator('#powerEmpty').is_visible()
    assert page.locator('#metricSold').inner_text() == '—'
    page.locator('#emptyReset').click()
    page.wait_for_function("document.querySelector('#metricShowings').textContent !== '0'")
    assert rows.count() == initial
    page.locator('[data-preset="busy"]').click()
    assert rows.evaluate_all("rows => rows.every(r => Number(r.dataset.filled) >= 70)")
    page.locator('[data-preset="quiet"]').click()
    assert rows.evaluate_all("rows => rows.every(r => r.dataset.filled !== '' && Number(r.dataset.filled) < 50 && r.dataset.onSale === 'true')")
    page.locator('[data-preset="all"]').click()
    title = rows.first.get_attribute('data-title')
    page.locator('#searchInput').fill(title)
    assert rows.count() > 0
    assert rows.evaluate_all('(rows, title) => rows.every(r => r.dataset.title.toLowerCase().includes(title.toLowerCase()))', title)
    page.locator('#searchInput').fill('')
    venue = rows.first.get_attribute('data-venue')
    page.locator('#roomFilter').select_option(venue)
    assert rows.evaluate_all('(rows, venue) => rows.every(r => r.dataset.venue === venue)', venue)
    page.locator('#roomFilter').select_option('all')
    page.locator('#modeFilter').select_option('reserved')
    assert rows.evaluate_all("rows => rows.every(r => r.dataset.mode === 'reserved')")
    page.locator('#modeFilter').select_option('all')
    for field, descending in [('left',False), ('filled',True), ('velocity',True), ('price',False)]:
        page.locator('#sortField').select_option(field)
        values = rows.evaluate_all('(rows, field) => rows.map(r => r.dataset[field] === "" ? null : Number(r.dataset[field]))', field)
        known = [v for v in values if v is not None]
        assert known == sorted(known, reverse=descending), f'Incorrect {field} sort'
        assert values == known + [None] * (len(values) - len(known)), 'Unknown values should sort last'
    signal = page.locator('.day-signal').first
    date = signal.get_attribute('data-date')
    signal.click()
    assert rows.evaluate_all('(rows, date) => rows.every(r => r.dataset.starts.startsWith(date))', date)
    assert page.locator('#metricShowings').inner_text() == str(rows.count())
    signal.click()
    page.locator('button[type="reset"]').click()
    page.wait_for_function("document.querySelector('#sortField').value === 'starts'")


def check_schedule(page):
    page.locator('#dayFilter').select_option('all')
    page.locator('#capacityFilter').select_option('busy')
    rows = page.locator('.movie:visible')
    assert rows.evaluate_all("rows => rows.every(r => Number(r.dataset.full) >= 50)")
    page.locator('#capacityFilter').select_option('all')
    venue = rows.first.get_attribute('data-movie-cinema')
    page.locator('#venueFilter').select_option(venue)
    assert rows.evaluate_all('(rows, venue) => rows.every(r => r.dataset.movieCinema === venue)', venue)
    page.locator('#venueFilter').select_option('all')
    page.locator('#groupFilter').select_option('by-movie')
    assert page.locator('.movie-group:visible').count() > 0
    assert page.locator('.day:visible').count() == 0
    assert_layout(page)
    button = page.locator('.other-times-btn:visible').first
    button.click()
    dialog = page.locator('#otherTimesDialog')
    assert dialog.is_visible()
    assert_layout(page)
    link = dialog.locator('.other-times-link').first
    target = link.get_attribute('href')
    link.click()
    assert not dialog.is_visible()
    assert page.locator(target).is_visible(), 'Other times must reveal a row hidden by filters'
    page.locator('#groupFilter').select_option('by-day')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--engines', nargs='+', default=['chromium','firefox','webkit'])
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        for engine in args.engines:
            browser = getattr(p, engine).launch()
            for width in (1280, 390, 768, 1024, 320):
                page = browser.new_page(viewport={'width':width,'height':900}, reduced_motion='reduce')
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                for name in ('index','power'):
                    page.goto(args.url.rstrip('/') + '/' + name + '.html')
                    page.wait_for_load_state('load')
                    assert_layout(page)
                    if width in (1280,390):
                        page.screenshot(path=str(out/f'{engine}-{name}-{width}.png'))
                        if name == 'power':
                            check_power(page)
                            page.locator('#board').evaluate("e => e.scrollIntoView({block:'start'})")
                            page.screenshot(path=str(out/f'{engine}-{name}-board-{width}.png'))
                        else:
                            check_schedule(page)
                    assert not errors, f'{engine}/{name}: {errors}'
                    print(f'PASS {engine} {name} {width}px', flush=True)
                page.close()
            browser.close()


if __name__ == '__main__':
    main()
