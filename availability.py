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

import os
import sqlite3
from datetime import datetime, timedelta

import requests

API_BASE_DEFAULT = "https://prod3.agileticketing.net/api/sales.svc/json"
# Type 1 is a showing (a single screening), as opposed to a show/package
ITEM_TYPE_SHOWING = 1
# Only record showings starting inside this window; past ones can't be
# bought and far-future ones have barely sold anything yet.
LOOKAHEAD_DAYS = 14
REQUEST_TIMEOUT_SECONDS = 30

# Looked for in this order; first file that exists is read. Keep these
# outside the repository - the keys are as sensitive as passwords.
CREDENTIAL_FILES = (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    "/etc/carolina-scraper/api.env",
    os.path.expanduser("~/.config/carolina-scraper/api.env"),
)


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
    now = datetime.now()
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

    conn.commit()
    conn.close()


def window_bounds(lookahead_days=LOOKAHEAD_DAYS):
    """The period we care about: from now to the lookahead cutoff."""
    now = datetime.now()
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
    reserved = sum(1 for s in snapshots if s["status"] == "reserved")
    print(f"Linked {linked} showtimes; availability recorded for "
          f"{len(snapshots)} showings ({reserved} reserved seating, "
          f"{len(snapshots) - reserved} general admission)")
    return {"linked": linked, "checked": len(snapshots), "reserved": reserved}


if __name__ == "__main__":
    import argparse
    import json
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
