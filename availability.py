"""
Seat availability for Carolina Theatre showings, via the Agile Ticketing
Sales API.

The theatre's ticketing system publishes inventory directly, so one request
covers every showing in a date range:

    GET {API_BASE}/ItemList?type=1&startDate=...&endDate=...
      -> [{ID, Name, StartDateTime, VenueName, HasReservedSeating,
            AvailableInventory, SoldInventory, HoldInventory,
            TotalInventory, ...}, ...]

AvailableInventory / TotalInventory is the share still for sale, and
SoldInventory is what has actually been bought - so unlike the seat maps
this separates real sales from seats the theatre is holding back. It also
covers general admission showings, which have no seat map at all.

Credentials come from the environment (see load_credentials); they are never
stored in this repository. Without them this module does nothing, and the
rest of the scraper carries on as normal.
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import requests

API_BASE_DEFAULT = "https://prod3.agileticketing.net/api/sales.svc/json"
# Showtimes are stored in theatre-local time, but the server runs on UTC.
# Using a naive now() there would treat the next few hours of showings as
# already past and skip them. EST vs EDT should be close enough.
THEATRE_TZ = timezone(timedelta(hours=-4))
# Type 1 is a showing (a single screening), as opposed to a show/package
ITEM_TYPE_SHOWING = 1
# Only record showings starting inside this window; past ones can't be
# bought and far-future ones have barely sold anything yet.
LOOKAHEAD_DAYS = 14
REQUEST_TIMEOUT_SECONDS = 30
# Prices and order limits hardly ever change, so re-read them at most
# this often per showing
DETAILS_STALE_DAYS = 7
# Pause between the per-showing detail calls, to stay gentle
DETAIL_DELAY_SECONDS = 0.3
# Cap on detail lookups per run so a big new listing spreads over runs
MAX_DETAIL_FETCHES = 80

# Looked for in this order; first file that exists is read. Keep these
# outside the repository - the keys are as sensitive as passwords.
CREDENTIAL_FILES = (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    "/etc/carolina-scraper/api.env",
    os.path.expanduser("~/.config/carolina-scraper/api.env"),
)


def theatre_now():
    """Current time where the theatre is, as a naive datetime to compare
    against the naive values stored in the database."""
    return datetime.now(THEATRE_TZ).replace(tzinfo=None)


def load_credentials(env=None):
    """
    Read API credentials from the environment, falling back to a key=value
    file (see CREDENTIAL_FILES). Returns a dict, or None when the required
    keys are missing.
    """
    values = dict(env or os.environ)

    for path in CREDENTIAL_FILES:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    # Environment wins over the file
                    values.setdefault(key.strip(),
                                      value.strip().strip('"').strip("'"))
        except OSError as e:
            print(f"Warning: could not read {path}: {e}")
        break

    required = ("AGILE_APP_KEY", "AGILE_USER_KEY", "AGILE_CORP_ORG_ID")
    missing = [key for key in required if not values.get(key)]
    if missing:
        return None

    return {
        "app_key": values["AGILE_APP_KEY"],
        "user_key": values["AGILE_USER_KEY"],
        "corp_org_id": values["AGILE_CORP_ORG_ID"],
        "api_base": values.get("AGILE_API_BASE", API_BASE_DEFAULT),
        # Buyer type decides which prices/restrictions apply; the public
        # web buyer type is the right view of availability.
        "buyer_type_id": values.get("AGILE_BUYER_TYPE_ID", "1816"),
    }


def api_get(creds, method, params=None, session=None):
    """
    Call one Sales API method. Returns parsed JSON, or None on failure.

    The API answers errors with HTTP 202 and a {"Code":..,"Message":..}
    body rather than an HTTP error status, so that shape is checked too.
    """
    query = {
        "appKey": creds["app_key"],
        "userKey": creds["user_key"],
        "corpOrgID": creds["corp_org_id"],
    }
    query.update(params or {})

    getter = session or requests
    try:
        response = getter.get(f"{creds['api_base']}/{method}", params=query,
                              timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        print(f"Warning: {method} request failed: {e}")
        return None

    if response.status_code not in (200, 202):
        print(f"Warning: {method} returned HTTP {response.status_code}")
        return None

    try:
        payload = response.json()
    except ValueError:
        print(f"Warning: {method} returned a non-JSON response")
        return None

    if isinstance(payload, dict) and "Code" in payload and "Message" in payload:
        # Don't print the message verbatim in case it echoes a credential
        print(f"Warning: {method} error code {payload['Code']}: "
              f"{payload['Message']}")
        return None

    return payload


def parse_api_datetime(value):
    """Convert "2026-09-18T19:00:00" into our "YYYY-MM-DD HH:MM" format."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").strftime(
            "%Y-%m-%d %H:%M")
    except ValueError:
        print(f"Warning: could not parse API datetime '{value}'")
        return ""


def fetch_showings(creds, lookahead_days=LOOKAHEAD_DAYS, session=None):
    """
    Every showing in the window, with its inventory. One API call.
    Returns a list of dicts.
    """
    now = theatre_now()
    payload = api_get(creds, "ItemList", {
        "type": ITEM_TYPE_SHOWING,
        "startDate": now.strftime("%Y-%m-%d"),
        "endDate": (now + timedelta(days=lookahead_days)).strftime("%Y-%m-%d"),
    }, session=session)

    if not isinstance(payload, list):
        return []

    showings = []
    for item in payload:
        total = item.get("TotalInventory")
        showings.append({
            "showing_id": str(item.get("ID")),
            "title": item.get("Name") or "",
            "starts_at": parse_api_datetime(item.get("StartDateTime")),
            "venue": item.get("VenueName") or "",
            "seats_total": total,
            "seats_available": item.get("AvailableInventory"),
            "seats_sold": item.get("SoldInventory"),
            "seats_held": item.get("HoldInventory"),
            "status": ("reserved" if item.get("HasReservedSeating")
                       else "general_admission"),
            "sales_state": item.get("SalesState"),
            "sales_message": item.get("SalesMessage") or "",
        })
    return showings


def fetch_showing_availability(creds, showing_id, session=None):
    """
    Inventory for a single showing. Only used by the command line; bulk runs
    take everything from fetch_showings in one request.
    """
    payload = api_get(creds, "ItemGetAvailability", {
        "type": ITEM_TYPE_SHOWING,
        "itemID": showing_id,
        "buyerTypeID": creds["buyer_type_id"],
        "withSeats": "false",
    }, session=session)
    return payload if isinstance(payload, dict) else None


def pick_standard_price(prices):
    """
    The headline ticket price out of a showing's tiers.

    A showing usually lists Standard plus Senior/Student discounts. The
    standard adult ticket is the one to lead with, so prefer a tier named
    "Standard" and otherwise take the dearest.
    """
    if not prices:
        return None
    standard = [p for p in prices if "standard" in (p.get("name") or "").lower()]
    return max(standard or prices, key=lambda p: p.get("charged") or 0)


def fetch_showing_details(creds, showing_id, session=None):
    """
    Prices and order limits for one showing.

    Two calls, because neither endpoint has everything:
      ItemGetAvailability -> BasePrice (list) and FullPrice (charged)
      ItemListPrices      -> MinPerOrder/MaxPerOrder, ShowAvailableQty
    """
    details = {"prices": [], "min_per_order": None, "max_per_order": None,
               "show_available_qty": None, "sold_out_text": None}

    availability = api_get(creds, "ItemGetAvailability", {
        "type": ITEM_TYPE_SHOWING,
        "itemID": showing_id,
        "buyerTypeID": creds["buyer_type_id"],
        "withSeats": "false",
    }, session=session)

    if isinstance(availability, dict):
        for section in availability.get("Sections") or []:
            for price in section.get("Prices") or []:
                details["prices"].append({
                    "name": price.get("Name"),
                    "list": price.get("BasePrice"),
                    "charged": price.get("FullPrice"),
                    "service_fee": price.get("ServiceFeePrice"),
                    "tax": price.get("Tax"),
                })

    limits = api_get(creds, "ItemListPrices", {
        "type": ITEM_TYPE_SHOWING,
        "itemID": showing_id,
        "buyerTypeID": creds["buyer_type_id"],
    }, session=session)

    if isinstance(limits, list):
        for group in limits:
            if details["show_available_qty"] is None:
                details["show_available_qty"] = group.get("ShowAvailableQty")
                details["sold_out_text"] = group.get("SoldOutText") or None
            for price in group.get("Prices") or []:
                # Order limits are per price tier but in practice uniform;
                # take the widest range on offer.
                lo, hi = price.get("MinPerOrder"), price.get("MaxPerOrder")
                if lo is not None:
                    details["min_per_order"] = (lo if details["min_per_order"] is None
                                                else min(details["min_per_order"], lo))
                if hi is not None:
                    details["max_per_order"] = (hi if details["max_per_order"] is None
                                                else max(details["max_per_order"], hi))

    return details


def save_showings(db_name, showings):
    """
    Record the basics for each showing (from the single ItemList call),
    leaving any price details already stored in place.
    """
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    for showing in showings:
        cursor.execute('''
            INSERT INTO showings
                (showing_id, title, venue, starts_at, seat_mode,
                 sales_state, sales_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(showing_id) DO UPDATE SET
                title = excluded.title,
                venue = excluded.venue,
                starts_at = excluded.starts_at,
                seat_mode = excluded.seat_mode,
                sales_state = excluded.sales_state,
                sales_message = excluded.sales_message
        ''', (showing["showing_id"], showing["title"], showing["venue"],
              showing["starts_at"], showing["status"],
              showing.get("sales_state"), showing.get("sales_message")))

    conn.commit()
    conn.close()


def showings_needing_details(db_name, lookahead_days=LOOKAHEAD_DAYS,
                             stale_days=DETAILS_STALE_DAYS):
    """
    Upcoming showings whose prices we've never fetched, or fetched a while
    ago. Prices and limits barely change, so this keeps a steady-state run
    down to the handful of newly announced showings.
    """
    start, end = window_bounds(lookahead_days)
    cutoff = (theatre_now() - timedelta(days=stale_days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT showing_id FROM showings
        WHERE starts_at BETWEEN ? AND ?
          AND (details_updated_at IS NULL OR details_updated_at < ?)
        ORDER BY starts_at
    ''', (start, end, cutoff))
    ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ids


def save_showing_details(db_name, showing_id, details):
    """Store the prices and order limits for one showing."""
    standard = pick_standard_price(details["prices"])
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE showings SET
            list_price = ?, charged_price = ?,
            min_per_order = ?, max_per_order = ?,
            show_available_qty = ?, sold_out_text = ?,
            prices_json = ?, details_updated_at = ?
        WHERE showing_id = ?
    ''', (standard.get("list") if standard else None,
          standard.get("charged") if standard else None,
          details["min_per_order"], details["max_per_order"],
          None if details["show_available_qty"] is None
          else int(bool(details["show_available_qty"])),
          details["sold_out_text"],
          json.dumps(details["prices"]) if details["prices"] else None,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"), showing_id))
    conn.commit()
    conn.close()


def ensure_schema(db_name="movie_showtimes.db"):
    """Add the availability table and the columns it needs, if missing."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    columns = [row[1] for row in cursor.execute("PRAGMA table_info(showtimes)")]
    if "showing_id" not in columns:
        cursor.execute("ALTER TABLE showtimes ADD COLUMN showing_id TEXT")
        print("Added showtimes.showing_id")

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

    # The API separates real sales from seats the theatre holds back, which
    # the old seat-map scraping could not distinguish
    availability_columns = [row[1] for row in
                            cursor.execute("PRAGMA table_info(availability)")]
    for column in ("seats_sold", "seats_held"):
        if column not in availability_columns:
            cursor.execute(f"ALTER TABLE availability ADD COLUMN {column} INTEGER")
            print(f"Added availability.{column}")

    # Facts about a showing that barely move: prices, order limits, seating
    # mode, sale state. One row per showing, not a time series.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS showings (
            showing_id TEXT PRIMARY KEY,
            title TEXT,
            venue TEXT,
            starts_at TEXT,
            seat_mode TEXT,
            sales_state INTEGER,
            sales_message TEXT,
            list_price REAL,
            charged_price REAL,
            min_per_order INTEGER,
            max_per_order INTEGER,
            show_available_qty INTEGER,
            sold_out_text TEXT,
            prices_json TEXT,
            details_updated_at TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


def window_bounds(lookahead_days=LOOKAHEAD_DAYS):
    """The period we care about: from now to the lookahead cutoff."""
    now = theatre_now()
    cutoff = now + timedelta(days=lookahead_days)
    return (now.strftime("%Y-%m-%d %H:%M"), cutoff.strftime("%Y-%m-%d %H:%M"))


def link_showings_to_showtimes(db_name, showings):
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
            UPDATE showtimes SET showing_id = ?
            WHERE formatted_datetime = ? AND cinema = ?
              AND (showing_id IS NULL OR showing_id != ?)
        ''', (showing["showing_id"], showing["starts_at"], showing["venue"],
              showing["showing_id"]))
        updated += cursor.rowcount

    conn.commit()
    conn.close()
    return updated


def linked_showing_ids(db_name, lookahead_days=LOOKAHEAD_DAYS):
    """Showing ids attached to stored showtimes inside the window."""
    start, end = window_bounds(lookahead_days)
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT showing_id FROM showtimes
        WHERE showing_id IS NOT NULL
          AND formatted_datetime BETWEEN ? AND ?
    ''', (start, end))
    ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    return ids


def save_snapshots(db_name, snapshots):
    """Store one availability reading per showing."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    # Deliberately the server clock, not theatre time: this only records
    # when the check ran, and readers pick the newest row by string order.
    # Mixing the two clocks would make a fresh row sort below an older one.
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for snapshot in snapshots:
        cursor.execute('''
            INSERT OR REPLACE INTO availability
            (showing_id, checked_at, status, seats_total, seats_available,
             seats_sold, seats_held)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (snapshot["showing_id"], checked_at, snapshot["status"],
              snapshot["seats_total"], snapshot["seats_available"],
              snapshot.get("seats_sold"), snapshot.get("seats_held")))

    conn.commit()
    conn.close()
    return len(snapshots)


def update_availability(db_name, showtimes=None, lookahead_days=LOOKAHEAD_DAYS,
                        session=None):
    """
    Record how full every upcoming showing is.

    showtimes is accepted for compatibility with the scraper's call and is
    not needed: the API supplies showing ids, start times and venues itself.
    """
    creds = load_credentials()
    if not creds:
        print("No ticketing API credentials configured; skipping availability")
        print("  (set AGILE_APP_KEY, AGILE_USER_KEY and AGILE_CORP_ORG_ID)")
        return {"linked": 0, "checked": 0, "reserved": 0}

    ensure_schema(db_name)

    showings = fetch_showings(creds, lookahead_days, session=session)
    if not showings:
        print("No showings returned by the ticketing API")
        return {"linked": 0, "checked": 0, "reserved": 0}

    linked = link_showings_to_showtimes(db_name, showings)

    # The API also lists concerts and comedy shows that aren't on the film
    # pages; only record what our showtimes actually reference.
    wanted = linked_showing_ids(db_name, lookahead_days)
    snapshots = [s for s in showings if s["showing_id"] in wanted]

    for snapshot in sorted(snapshots, key=lambda s: s["starts_at"]):
        total = snapshot["seats_total"] or 0
        if total:
            remaining = snapshot["seats_available"] / total * 100
            sold = snapshot["seats_sold"]
            print(f"  {snapshot['starts_at']} {snapshot['title']} "
                  f"({snapshot['venue']}): {snapshot['seats_available']}/{total} "
                  f"left ({remaining:.0f}% remaining, {sold} sold"
                  f"{', %d held' % snapshot['seats_held'] if snapshot['seats_held'] else ''})")
        else:
            print(f"  {snapshot['starts_at']} {snapshot['title']} "
                  f"({snapshot['venue']}): no inventory reported")

    save_snapshots(db_name, snapshots)
    # Basics for every showing the API returned, including the concerts the
    # film pages don't list - the power dashboard shows those too
    save_showings(db_name, showings)

    priced = refresh_showing_details(db_name, creds, lookahead_days,
                                     session=session)

    reserved = sum(1 for s in snapshots if s["status"] == "reserved")
    print(f"Linked {linked} showtimes; availability recorded for "
          f"{len(snapshots)} showings ({reserved} reserved seating, "
          f"{len(snapshots) - reserved} general admission)")
    return {"linked": linked, "checked": len(snapshots), "reserved": reserved,
            "priced": priced}


def refresh_showing_details(db_name, creds, lookahead_days=LOOKAHEAD_DAYS,
                            session=None, limit=MAX_DETAIL_FETCHES):
    """
    Fetch prices and order limits for showings that lack them or whose
    figures have gone stale. Two API calls each, so this is deliberately
    incremental: a steady-state run only picks up newly announced showings.
    """
    pending = showings_needing_details(db_name, lookahead_days)[:limit]
    if not pending:
        return 0

    print(f"Reading prices for {len(pending)} showings")
    done = 0
    for showing_id in pending:
        details = fetch_showing_details(creds, showing_id, session=session)
        if details["prices"] or details["max_per_order"] is not None:
            save_showing_details(db_name, showing_id, details)
            done += 1
        time.sleep(DETAIL_DELAY_SECONDS)

    print(f"Prices recorded for {done} showings")
    return done


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Check Carolina Theatre showing availability")
    parser.add_argument("--showing",
                        help="Showing id to look up (from evtInfo=ID~GUID)")
    parser.add_argument("--list", action="store_true",
                        help="List every upcoming showing with its inventory")
    parser.add_argument("--db", default="movie_showtimes.db",
                        help="SQLite database for a bulk update")
    parser.add_argument("--bulk", action="store_true",
                        help="Record availability for showtimes in --db")
    parser.add_argument("--days", type=int, default=LOOKAHEAD_DAYS,
                        help=f"Days ahead to include (default {LOOKAHEAD_DAYS})")
    args = parser.parse_args()

    credentials = load_credentials()
    if not credentials:
        sys.exit("No credentials: set AGILE_APP_KEY, AGILE_USER_KEY and "
                 "AGILE_CORP_ORG_ID (or put them in .env)")

    if args.showing:
        print(json.dumps(fetch_showing_availability(credentials, args.showing),
                         indent=2))
    elif args.list:
        for showing in sorted(fetch_showings(credentials, args.days),
                              key=lambda s: s["starts_at"]):
            total = showing["seats_total"] or 0
            pct = f"{showing['seats_available'] / total * 100:5.1f}%" if total else "    ?"
            print(f"{showing['showing_id']:>9} {showing['starts_at']} "
                  f"{showing['venue']:14} {pct} left  "
                  f"{showing['seats_available']:4}/{total:<5} "
                  f"sold={showing['seats_sold']:<4} {showing['title'][:34]}")
    elif args.bulk:
        update_availability(args.db, lookahead_days=args.days)
    else:
        parser.print_help()
        sys.exit(1)
