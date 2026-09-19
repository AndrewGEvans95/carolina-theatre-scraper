"""
Power dashboard generator.

Builds power.html (and power.json beside it) from the database: every
upcoming showing with its inventory, fill, pricing, seating mode, order
limits and freshness, plus how fast it has been selling when there is
enough snapshot history to say.

The main schedule answers "what shall I watch". This answers "what is
actually going on with this showing", which is a different job, so it gets
its own page rather than cluttering the schedule.

Velocity is one column among several. With a single snapshot the inventory
and pricing are still the point; deltas appear once history exists and show
as a dash until then, never as a fabricated zero.
"""

import argparse
import json
import os
import sqlite3
import shutil

from power_view import render_dashboard
from collections import Counter
from datetime import datetime, timedelta, timezone

# Matches availability.py: showtimes are stored in theatre-local time while
# the server runs on UTC.
THEATRE_TZ = timezone(timedelta(hours=-4))
LOOKAHEAD_DAYS = 14
TICKET_URL = ("https://tickets.carolinatheatre.org/websales/pages/"
              "Buy.aspx?evtInfo={showing_id}~{org_guid}")
# Public identifier from the theatre's own ticket links, used when the
# database has no org_guid recorded
ORG_GUID_DEFAULT = "05de892e-fe79-4e77-8f75-9f03e89f9235"


def theatre_now():
    return datetime.now(THEATRE_TZ).replace(tzinfo=None)


def org_guid(conn):
    """
    The organisation id that ticket links need.

    Preferred from the stored showtimes (most common value, in case a stray
    row disagrees), falling back to the known public id for databases that
    never recorded it. It appears in every ticket URL on the theatre's own
    site, so it isn't a secret.
    """
    columns = [row[1] for row in conn.execute("PRAGMA table_info(showtimes)")]
    if "org_guid" in columns:
        guids = Counter(row[0] for row in conn.execute(
            "SELECT org_guid FROM showtimes WHERE org_guid IS NOT NULL"))
        if guids:
            return guids.most_common(1)[0][0]
    return ORG_GUID_DEFAULT


def sold_deltas(conn, showing_id, latest_checked_at, seats_sold):
    """
    How many more tickets have sold over the last 6 and 24 hours.

    Compares the newest reading with the newest one at least that old. A
    showing checked for the first time has nothing to compare against, so
    both come back None rather than 0 - "no data" and "no sales" are
    different facts.
    """
    deltas = {}
    if seats_sold is None or not latest_checked_at:
        return {"6h": None, "24h": None}

    try:
        latest = datetime.strptime(latest_checked_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {"6h": None, "24h": None}

    for label, hours in (("6h", 6), ("24h", 24)):
        cutoff = (latest - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute('''
            SELECT seats_sold FROM availability
            WHERE showing_id = ? AND checked_at <= ? AND seats_sold IS NOT NULL
            ORDER BY checked_at DESC LIMIT 1
        ''', (showing_id, cutoff)).fetchone()
        deltas[label] = seats_sold - row[0] if row and row[0] is not None else None

    return deltas


def load_showings(db_name="movie_showtimes.db", lookahead_days=LOOKAHEAD_DAYS):
    """Every upcoming showing with its latest inventory and its details."""
    now = theatre_now()
    start = now.strftime("%Y-%m-%d %H:%M")
    end = (now + timedelta(days=lookahead_days)).strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect(db_name)
    guid = org_guid(conn)

    rows = conn.execute('''
        SELECT s.showing_id, s.title, s.venue, s.starts_at, s.seat_mode,
               s.sales_state, s.sales_message, s.list_price, s.charged_price,
               s.min_per_order, s.max_per_order, s.show_available_qty,
               s.prices_json,
               a.checked_at, a.seats_total, a.seats_available, a.seats_sold,
               a.seats_held
        FROM showings s
        LEFT JOIN (
            SELECT showing_id, checked_at, seats_total, seats_available,
                   seats_sold, seats_held,
                   ROW_NUMBER() OVER (
                       PARTITION BY showing_id ORDER BY checked_at DESC
                   ) AS recency
            FROM availability
        ) a ON a.showing_id = s.showing_id AND a.recency = 1
        WHERE s.starts_at BETWEEN ? AND ?
        ORDER BY s.starts_at
    ''', (start, end)).fetchall()

    showings = []
    for row in rows:
        (showing_id, title, venue, starts_at, seat_mode, sales_state,
         sales_message, list_price, charged_price, min_per_order, max_per_order,
         show_available_qty, prices_json, checked_at, seats_total,
         seats_available, seats_sold, seats_held) = row

        total = seats_total or 0
        pct_filled = round(seats_sold / total * 100, 1) if total and seats_sold is not None else None
        pct_remaining = round(seats_available / total * 100, 1) if total and seats_available is not None else None
        deltas = sold_deltas(conn, showing_id, checked_at, seats_sold)
        fee = (round(charged_price - list_price, 2)
               if charged_price is not None and list_price is not None else None)

        showings.append({
            "showing_id": showing_id,
            "title": title or "",
            "venue": venue or "",
            "starts_at": starts_at or "",
            "seats_total": seats_total,
            "seats_available": seats_available,
            "seats_sold": seats_sold,
            "seats_hold": seats_held,
            "pct_filled": pct_filled,
            "pct_remaining": pct_remaining,
            "has_reserved_seating": seat_mode == "reserved",
            "list_price": list_price,
            "charged_price": charged_price,
            "fee": fee,
            "prices": json.loads(prices_json) if prices_json else [],
            "min_per_order": min_per_order,
            "max_per_order": max_per_order,
            "show_available_qty_on_web": (None if show_available_qty is None
                                          else bool(show_available_qty)),
            "on_sale": sales_state == 2 if sales_state is not None else None,
            "sales_state": sales_state,
            "sales_message": sales_message or "",
            "checked_at": checked_at,
            "sold_delta_6h": deltas["6h"],
            "sold_delta_24h": deltas["24h"],
            "ticket_url": (TICKET_URL.format(showing_id=showing_id, org_guid=guid)
                           if guid else None),
        })

    conn.close()
    return showings


def totals(showings):
    """Org-level snapshot for the HUD."""
    counted = [s for s in showings if s["seats_total"]]
    sold = sum(s["seats_sold"] or 0 for s in counted)
    capacity = sum(s["seats_total"] or 0 for s in counted)
    return {
        "showings": len(showings),
        "with_inventory": len(counted),
        "seats_sold": sold,
        "seats_left": sum(s["seats_available"] or 0 for s in counted),
        "capacity": capacity,
        "pct_filled": round(sold / capacity * 100, 1) if capacity else None,
    }


def build_json(showings, lookahead_days):
    return {
        "generated_at": theatre_now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "America/New_York (fixed -04:00)",
        "window_days": lookahead_days,
        "totals": totals(showings),
        "showings": showings,
    }


def render_html(showings, template_path, lookahead_days):
    generated = theatre_now().strftime("%b %d, %Y · %I:%M%p ET").replace(" 0", " ")
    return render_dashboard(showings, template_path, lookahead_days, generated)


def generate(db_name="movie_showtimes.db", output_dir=".",
             template_path=None, lookahead_days=LOOKAHEAD_DAYS):
    """Write power.html and power.json into output_dir."""
    here = os.path.dirname(os.path.abspath(__file__))
    template_path = template_path or os.path.join(here, "power_template.html")

    showings = load_showings(db_name, lookahead_days)
    print(f"Power dashboard: {len(showings)} showings in the next "
          f"{lookahead_days} days")

    os.makedirs(output_dir, exist_ok=True)
    for asset in ("interface.css", "power.js"):
        source = os.path.join(here, asset)
        destination = os.path.join(output_dir, asset)
        if os.path.abspath(source) != os.path.abspath(destination):
            shutil.copy2(source, destination)
        os.chmod(destination, 0o644)

    json_path = os.path.join(output_dir, "power.json")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(build_json(showings, lookahead_days), handle, indent=2)
    os.chmod(json_path, 0o644)
    print(f"Wrote {json_path}")

    html_path = os.path.join(output_dir, "power.html")
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(render_html(showings, template_path, lookahead_days))
    os.chmod(html_path, 0o644)
    print(f"Wrote {html_path}")

    return len(showings)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate the power dashboard page and its JSON")
    parser.add_argument("-o", "--output-dir", default=".",
                        help="Where to write power.html and power.json")
    parser.add_argument("--db", default="movie_showtimes.db",
                        help="SQLite database to read")
    parser.add_argument("--days", type=int, default=LOOKAHEAD_DAYS,
                        help=f"Days ahead to include (default {LOOKAHEAD_DAYS})")
    args = parser.parse_args()

    generate(args.db, args.output_dir, lookahead_days=args.days)
