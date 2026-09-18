"""
Seat availability for Carolina Theatre showings (Agile Ticketing).

Each film page on carolinatheatre.org links to the ticketing system:

    info.aspx?evtinfo=<EVENT_ID>~<ORG_GUID>      one page lists every showing
      -> Buy.aspx?evtInfo=<SHOWING_ID>~<ORG_GUID>  the seat map for one showing

The seat map page carries the numbers we want on the <svg> tag itself:

    <svg class="agl-svgseatsimg" data-availpct="38" data-seatcount="53">
      <rect class="agl-avail" data-seatid="..." .../>   one per available seat

seats_available / seats_total is the percentage still for sale; the rest is
unavailable (sold, comped, or held back by the theatre).

Only showings sold with reserved seating have a seat map. That is a per
showing choice rather than a property of the room: first-run films are
usually reserved, while repertory titles are sold general admission even in
the same cinema. General admission showings offer a quantity dropdown
instead, which is a per-order purchase limit and says nothing about how much
is left, so they report no numbers rather than a misleading zero.

Both pages are plain server-rendered HTML, but the ticketing site is behind
a JavaScript challenge that answers everything else with a small stub page.
So a browser loads one page to earn the challenge cookies, and those cookies
are then reused for ordinary HTTP requests - far cheaper than driving the
browser once per showing.
"""

import re
import sqlite3
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

TICKETS_PAGES = "https://tickets.carolinatheatre.org/websales/pages"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Only check showings starting inside this window; past showings can't be
# bought and far-future ones have barely sold anything yet.
LOOKAHEAD_DAYS = 14
# Hard cap so a long listing can't turn one run into an hour of requests.
MAX_SHOWINGS_PER_RUN = 200
# Pause between ticketing requests to stay gentle on their site.
REQUEST_DELAY_SECONDS = 0.7

EVENT_REF_RE = re.compile(r"info\.aspx\?evtinfo=(\d+)~([0-9a-fA-F-]{36})")
SEATCOUNT_RE = re.compile(r"""data-seatcount=["'](\d+)["']""")
AVAIL_SEAT_RE = re.compile(r"""class=["']agl-avail["']""")


def extract_event_ref(html):
    """
    Find the ticketing event a film page links to.
    Returns (event_id, org_guid), or None for films not on sale yet.
    """
    match = EVENT_REF_RE.search(html or "")
    return (match.group(1), match.group(2)) if match else None


def parse_showing_datetime(value):
    """
    Convert Agile's "9/18/26 07:00 P" into our "YYYY-MM-DD HH:MM" format.
    """
    value = (value or "").strip()
    if not value:
        return ""
    # "P"/"A" are abbreviated AM/PM markers
    normalized = re.sub(r"\b([AP])$", r"\1M", value)
    for fmt in ("%m/%d/%y %I:%M %p", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    print(f"Warning: could not parse showing datetime '{value}'")
    return ""


def make_driver():
    """Headless Chrome, used only to answer the ticketing site's challenge."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1280,900")
    options.add_argument(f"--user-agent={USER_AGENT}")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                            options=options)


def is_challenge_stub(html):
    """
    True when the challenge answered instead of the real page. The stub is a
    few hundred bytes that only loads an Incapsula script.
    """
    return len(html) < 2000 and "Incapsula" in html


def new_ticketing_session():
    """
    Load one ticketing page in a browser so the challenge sets its cookies,
    then hand those cookies to a plain requests session.
    Returns None if the browser could not be started.
    """
    driver = None
    try:
        driver = make_driver()
        driver.get(f"{TICKETS_PAGES}/info.aspx")
        time.sleep(2)
        cookies = driver.get_cookies()
    except Exception as e:
        print(f"Warning: could not start a ticketing session: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    for cookie in cookies:
        session.cookies.set(cookie["name"], cookie["value"],
                            domain=".carolinatheatre.org")
    return session


def fetch_ticketing_page(session, url):
    """
    GET a ticketing page, renewing the challenge cookies once if they have
    gone stale. Returns (html, session) since the session may be replaced.
    """
    for attempt in (1, 2):
        try:
            response = session.get(url, timeout=30)
        except requests.RequestException as e:
            print(f"Warning: request failed for {url}: {e}")
            return "", session

        if response.status_code != 200:
            print(f"Warning: {url} returned {response.status_code}")
            return "", session

        if not is_challenge_stub(response.text):
            return response.text, session

        if attempt == 1:
            print("Ticketing session expired; renewing")
            renewed = new_ticketing_session()
            if not renewed:
                return "", session
            session = renewed

    print(f"Warning: still blocked by the ticketing challenge for {url}")
    return "", session


def fetch_showings(event_id, org_guid, session):
    """
    Read every showing of one event from info.aspx.
    Returns (showings, session); each showing has showing_id, starts_at,
    venue, title and on_sale.
    """
    url = f"{TICKETS_PAGES}/info.aspx?evtinfo={event_id}~{org_guid}"
    html, session = fetch_ticketing_page(session, url)
    if not html:
        return [], session

    soup = BeautifulSoup(html, "html.parser")
    showings = []

    for item in soup.select("div.Showing"):
        group = item.select_one("div.ButtonGroup[data-agl_pid]")
        if not group:
            continue

        pid = group.get("data-agl_pid", "")
        if not pid.startswith("Showing-"):
            continue

        buy_link = item.select_one("a.BuyLink")
        buy_classes = buy_link.get("class", []) if buy_link else []
        venue_elem = item.select_one("span.Venue")

        showings.append({
            "showing_id": pid.split("-", 1)[1],
            "starts_at": parse_showing_datetime(group.get("data-agl_date")),
            "venue": venue_elem.get_text(strip=True) if venue_elem else "",
            "title": group.get("data-agl_name", ""),
            # PastEvent covers showings that have already started
            "on_sale": "PastEvent" not in buy_classes,
        })

    if not showings:
        print(f"Warning: no showings parsed for event {event_id}")

    return showings, session


def fetch_seat_counts(session, showing_id, org_guid):
    """
    Read one seat map.

    Returns (counts, session). counts has a status and, for reserved
    seating, seats_total and seats_available:
      reserved           - counted successfully
      general_admission  - no seat map, quantity dropdown only
      multi_section      - seat map covers one section of several; a total
                           would be wrong, so no numbers are reported
      no_data            - page didn't render either shape (not on sale, etc.)
    """
    url = f"{TICKETS_PAGES}/Buy.aspx?evtInfo={showing_id}~{org_guid}&"
    html, session = fetch_ticketing_page(session, url)
    blank = {"status": "no_data", "seats_total": None, "seats_available": None}
    if not html:
        return blank, session

    seatcount = SEATCOUNT_RE.search(html)
    if seatcount:
        # data-seatcount describes the section on screen, so it is only a
        # house total when there is a single section to choose from.
        soup = BeautifulSoup(html, "html.parser")
        section_select = soup.select_one("select[id*='SectionList']")
        sections = section_select.select("option") if section_select else []
        if len(sections) > 1:
            return ({"status": "multi_section", "seats_total": None,
                     "seats_available": None}, session)

        return ({
            "status": "reserved",
            "seats_total": int(seatcount.group(1)),
            "seats_available": len(AVAIL_SEAT_RE.findall(html)),
        }, session)

    if "ddQuantity" in html:
        return ({"status": "general_admission", "seats_total": None,
                 "seats_available": None}, session)

    return blank, session


def ensure_schema(db_name="movie_showtimes.db"):
    """Add the availability table and showtimes.showing_id if missing."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    columns = [row[1] for row in cursor.execute("PRAGMA table_info(showtimes)")]
    if "showing_id" not in columns:
        cursor.execute("ALTER TABLE showtimes ADD COLUMN showing_id TEXT")
        print("Added showtimes.showing_id")
    # Stored with the showing so seat maps can be fetched on later runs
    # without re-reading it off a film page
    if "org_guid" not in columns:
        cursor.execute("ALTER TABLE showtimes ADD COLUMN org_guid TEXT")
        print("Added showtimes.org_guid")

    # One row per check, so availability can be compared over time
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS availability (
            showing_id TEXT NOT NULL,
            checked_at TIMESTAMP NOT NULL,
            status TEXT NOT NULL,
            seats_total INTEGER,
            seats_available INTEGER,
            PRIMARY KEY (showing_id, checked_at)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_availability_showing
        ON availability (showing_id, checked_at DESC)
    ''')

    conn.commit()
    conn.close()


def window_bounds(lookahead_days=LOOKAHEAD_DAYS):
    """The period we care about: from now to the lookahead cutoff."""
    now = datetime.now()
    cutoff = now + timedelta(days=lookahead_days)
    return (now.strftime("%Y-%m-%d %H:%M"), cutoff.strftime("%Y-%m-%d %H:%M"))


def events_needing_showings(db_name, showtimes, lookahead_days=LOOKAHEAD_DAYS):
    """
    Events whose upcoming showtimes don't have a showing id yet.

    Showing ids never change, so once a film's showtimes are linked its
    info.aspx page doesn't need fetching again - in the steady state that is
    only newly announced showings.
    """
    start, end = window_bounds(lookahead_days)
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT link FROM showtimes
        WHERE showing_id IS NULL
          AND formatted_datetime BETWEEN ? AND ?
    ''', (start, end))
    unlinked_links = {row[0] for row in cursor.fetchall()}
    conn.close()

    events = {}
    for showtime in showtimes:
        ref = showtime.get("event_ref")
        if ref and showtime.get("link") in unlinked_links:
            events[ref] = True
    return list(events)


def link_showings_to_showtimes(db_name, showings, org_guid):
    """
    Attach showing ids to stored showtimes, matching on start time and venue.
    Returns the number of showtimes updated.
    """
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    updated = 0

    for showing in showings:
        if not showing["starts_at"]:
            continue

        # Start time plus room is enough to identify a showing: one room can
        # only run one film at a time. Titles are not compared because the
        # ticketing system and the website word them differently.
        cursor.execute('''
            UPDATE showtimes SET showing_id = ?, org_guid = ?
            WHERE formatted_datetime = ? AND cinema = ?
              AND (showing_id IS NULL OR showing_id != ? OR org_guid IS NULL)
        ''', (showing["showing_id"], org_guid, showing["starts_at"],
              showing["venue"], showing["showing_id"]))
        updated += cursor.rowcount

    conn.commit()
    conn.close()
    return updated


def showings_to_check(db_name, lookahead_days=LOOKAHEAD_DAYS,
                      limit=MAX_SHOWINGS_PER_RUN):
    """Stored showings starting between now and the lookahead cutoff."""
    start, end = window_bounds(lookahead_days)
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT showing_id, org_guid, formatted_datetime, title, cinema
        FROM showtimes
        WHERE showing_id IS NOT NULL AND org_guid IS NOT NULL
          AND formatted_datetime BETWEEN ? AND ?
        ORDER BY formatted_datetime
        LIMIT ?
    ''', (start, end, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


def save_snapshots(db_name, snapshots):
    """Store one availability reading per showing."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for snapshot in snapshots:
        cursor.execute('''
            INSERT OR REPLACE INTO availability
            (showing_id, checked_at, status, seats_total, seats_available)
            VALUES (?, ?, ?, ?, ?)
        ''', (snapshot["showing_id"], checked_at, snapshot["status"],
              snapshot["seats_total"], snapshot["seats_available"]))

    conn.commit()
    conn.close()
    return len(snapshots)


def update_availability(db_name, showtimes, lookahead_days=LOOKAHEAD_DAYS,
                        limit=MAX_SHOWINGS_PER_RUN, session=None):
    """
    Map scraped showtimes to ticketing showings, then record how many seats
    each upcoming showing has left.
    """
    ensure_schema(db_name)

    pending_events = events_needing_showings(db_name, showtimes, lookahead_days)
    pending = showings_to_check(db_name, lookahead_days, limit)

    if not pending_events and not pending:
        print("Nothing to check: no upcoming showings linked to ticketing")
        return {"linked": 0, "checked": 0, "reserved": 0}

    if session is None:
        session = new_ticketing_session()
    if session is None:
        return {"linked": 0, "checked": 0, "reserved": 0}

    # Look up showing ids for films we haven't linked yet
    linked = 0
    for event_id, org_guid in pending_events:
        showings, session = fetch_showings(event_id, org_guid, session)
        linked += link_showings_to_showtimes(db_name, showings, org_guid)
        time.sleep(REQUEST_DELAY_SECONDS)

    if linked:
        pending = showings_to_check(db_name, lookahead_days, limit)
    print(f"Linked {linked} showtimes to ticketing showings; "
          f"{len(pending)} upcoming showings to check")
    if not pending:
        return {"linked": linked, "checked": 0, "reserved": 0}

    snapshots = []
    for showing_id, org_guid, starts_at, title, cinema in pending:
        counts, session = fetch_seat_counts(session, showing_id, org_guid)
        counts["showing_id"] = showing_id
        snapshots.append(counts)

        if counts["status"] == "reserved" and counts["seats_total"]:
            remaining = counts["seats_available"] / counts["seats_total"] * 100
            print(f"  {starts_at} {title} ({cinema}): "
                  f"{counts['seats_available']}/{counts['seats_total']} seats left "
                  f"({remaining:.0f}% remaining, {100 - remaining:.0f}% sold)")
        else:
            print(f"  {starts_at} {title} ({cinema}): {counts['status']}")

        time.sleep(REQUEST_DELAY_SECONDS)

    save_snapshots(db_name, snapshots)
    reserved = sum(1 for s in snapshots if s["status"] == "reserved")
    print(f"Availability recorded for {len(snapshots)} showings "
          f"({reserved} with seat counts)")
    return {"linked": linked, "checked": len(snapshots), "reserved": reserved}
