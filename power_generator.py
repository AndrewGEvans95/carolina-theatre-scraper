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
import html
import json
import os
import sqlite3
from collections import Counter, defaultdict
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
# Sales states from the ticketing API; 2 is on sale now
SALES_STATES = {
    1: "BEFORE SALES",
    2: "ON SALE",
    3: "SALES CLOSED",
    4: "AFTER EVENT",
    5: "CUSTOM MESSAGE",
}
INSIGHT_LIMIT = 5
# How much snapshot history the trend line draws on
HISTORY_DAYS = 7


def theatre_now():
    return datetime.now(THEATRE_TZ).replace(tzinfo=None)


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def money(value):
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "—"


def signed(value):
    if value is None:
        return "—"
    return f"+{value}" if value > 0 else str(value)


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


def fill_level(pct_filled):
    """Colour band for a fill bar, matching the schedule page."""
    if pct_filled is None:
        return "unknown"
    if pct_filled >= 90:
        return "full"
    if pct_filled >= 70:
        return "high"
    if pct_filled >= 40:
        return "mid"
    return "low"


def load_history(conn, days=HISTORY_DAYS):
    """
    Every sold-count reading of the last few days, grouped by showing.

    One query for the lot: the page needs each showing's whole series for
    its trend line, and the deltas fall out of the same data.
    """
    since = (theatre_now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    series = defaultdict(list)
    rows = conn.execute(
        "SELECT showing_id, checked_at, seats_sold FROM availability "
        "WHERE seats_sold IS NOT NULL AND checked_at >= ? "
        "ORDER BY checked_at", (since,))
    for showing_id, checked_at, sold in rows:
        series[showing_id].append((checked_at, sold))
    return series


def sold_deltas(points):
    """
    How many tickets sold in the last 6 and 24 hours.

    Compares the newest reading with the newest one at least that old. With
    nothing old enough to compare against the answer is None, not 0: "no
    data" and "no sales" are different facts. Values can be negative -
    refunds happen, and the box office figures reflect them.
    """
    if not points:
        return {"6h": None, "24h": None}

    try:
        latest_at = datetime.strptime(points[-1][0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {"6h": None, "24h": None}

    latest_sold = points[-1][1]
    deltas = {}
    for label, hours in (("6h", 6), ("24h", 24)):
        cutoff = latest_at - timedelta(hours=hours)
        earlier = [sold for at, sold in points
                   if datetime.strptime(at, "%Y-%m-%d %H:%M:%S") <= cutoff]
        deltas[label] = latest_sold - earlier[-1] if earlier else None
    return deltas


def sparkline(points, width=64, height=18):
    """
    A small trend line of tickets sold over time.

    Scaled to the showing's own range rather than to its capacity: the
    shape of the selling is the point, and the exact numbers sit in the
    columns beside it. Needs two readings before it can draw anything.
    """
    if len(points) < 2:
        return '<span class="nodata">-</span>'

    values = [sold for _, sold in points]
    low, high = min(values), max(values)
    span = (high - low) or 1
    step = width / (len(values) - 1)

    coords = " ".join(
        f"{i * step:.1f},{height - 1 - (v - low) / span * (height - 2):.1f}"
        for i, v in enumerate(values))
    last_y = height - 1 - (values[-1] - low) / span * (height - 2)

    hours = 0
    try:
        hours = round((datetime.strptime(points[-1][0], "%Y-%m-%d %H:%M:%S")
                       - datetime.strptime(points[0][0], "%Y-%m-%d %H:%M:%S")
                       ).total_seconds() / 3600)
    except ValueError:
        pass
    tip = (f"{len(values)} readings over {hours}h: "
           f"{values[0]} to {values[-1]} tickets sold")

    return (f'<svg class="spark" viewBox="0 0 {width + 3} {height}" '
            f'width="{width + 3}" height="{height}" role="img" '
            f'aria-label="{esc(tip)}"><title>{esc(tip)}</title>'
            f'<polyline points="{coords}" />'
            f'<circle cx="{width:.1f}" cy="{last_y:.1f}" r="1.8" /></svg>')


def load_showings(db_name="movie_showtimes.db", lookahead_days=LOOKAHEAD_DAYS):
    """Every upcoming showing with its latest inventory and its details."""
    now = theatre_now()
    start = now.strftime("%Y-%m-%d %H:%M")
    end = (now + timedelta(days=lookahead_days)).strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect(db_name)
    guid = org_guid(conn)
    history = load_history(conn)

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
        points = history.get(showing_id, [])
        deltas = sold_deltas(points)
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
            "sold_history": [[at, sold] for at, sold in points],
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


def insights(showings):
    """Short lists that point at the interesting rows in the board."""
    filled = [s for s in showings if s["pct_filled"] is not None]
    velocity = [s for s in showings if s["sold_delta_24h"] is not None]
    fees = [s for s in showings if s["fee"] is not None]

    return [
        ("FULLEST", sorted(filled, key=lambda s: -s["pct_filled"])[:INSIGHT_LIMIT],
         lambda s: f"{s['pct_filled']:.0f}% full"),
        ("EMPTIEST ON SALE",
         sorted([s for s in filled if s["on_sale"] is not False],
                key=lambda s: s["pct_filled"])[:INSIGHT_LIMIT],
         lambda s: f"{s['pct_filled']:.0f}% full"),
        ("MOVING FASTEST (24H)",
         sorted(velocity, key=lambda s: -s["sold_delta_24h"])[:INSIGHT_LIMIT],
         lambda s: f"{signed(s['sold_delta_24h'])} sold"),
        ("BIGGEST FEE GAP",
         sorted(fees, key=lambda s: -s["fee"])[:INSIGHT_LIMIT],
         lambda s: f"{money(s['list_price'])} → {money(s['charged_price'])}"),
    ]


def format_when(starts_at, compact=False):
    """
    "Fri, Sep 19 · 7:00pm", or "Fri 19 · 7:00pm" when compact - the table
    needs the date but can't afford the width of the long form.
    """
    try:
        when = datetime.strptime(starts_at, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return esc(starts_at)
    if compact:
        # Numeric in the table: it reads fine in a data column and buys
        # width for the film titles
        day = f"{when.month}/{when.day}"
    else:
        day = when.strftime("%a, %b %d").replace(" 0", " ")
    clock = when.strftime("%I:%M%p").lower().lstrip("0")
    return f"{day} · {clock}"


def house_rules(showings):
    """
    The facts that are the same for every showing.

    Order limits, the hidden-quantity policy and the sale state are
    identical across the listing, so stating them once beats repeating them
    on all sixty rows. Anything that varies stays in the table.
    """
    rules = []

    caps = {s["max_per_order"] for s in showings if s["max_per_order"]}
    if len(caps) == 1:
        rules.append(f"max {caps.pop()} tickets per order")

    hidden = [s["show_available_qty_on_web"] for s in showings
              if s["show_available_qty_on_web"] is not None]
    if hidden and all(h is False for h in hidden):
        rules.append("the theatre hides remaining counts on its own site")

    not_on_sale = [s for s in showings if s["on_sale"] is False]
    if showings and not not_on_sale:
        rules.append("all on sale")

    checked = sorted({s["checked_at"][:16] for s in showings if s["checked_at"]})
    if len(checked) == 1:
        rules.append(f"checked {checked[0][11:16]}")

    return " · ".join(rules)


def render_row(showing):
    """
    One table row. Numbers sit in aligned columns so a column can be read
    down the page; only fields that actually differ between showings are
    here, the constant ones are stated once above the table.
    """
    pct_filled = showing["pct_filled"]
    # Band from the same rounded figure the label shows, so a bar reading
    # "70%" isn't coloured as if it were 69%
    shown_pct = round(pct_filled) if pct_filled is not None else None
    level = fill_level(shown_pct)

    title = esc(showing["title"])
    if showing["ticket_url"]:
        title = (f"<a href=\"{esc(showing['ticket_url'])}\" target=\"_blank\" "
                 f"rel=\"noopener\" title=\"{esc(showing['title'])}\">{title}</a>")

    if shown_pct is None:
        fill_cell = '<span class="nodata">no data</span>'
    else:
        fill_cell = (f'<span class="fill" data-level="{level}" '
                     f'title="{shown_pct}% of capacity sold">'
                     f'<span class="fill-track">'
                     f'<span class="fill-bar" style="width:{pct_filled}%"></span>'
                     f'</span>'
                     f'<span class="fill-pct">{shown_pct}%</span></span>')

    sold = showing["seats_sold"]
    total = showing["seats_total"]
    seats = (f'<strong>{sold}</strong><span class="of">/{total}</span>'
             if sold is not None and total else "—")

    # Held seats are almost always zero; call them out only when they aren't
    held = showing["seats_hold"]
    left = showing["seats_available"]
    left_cell = "—" if left is None else str(left)
    if held:
        left_cell += f'<span class="held" title="{held} seats held back by the theatre">+{held} held</span>'

    list_cell = ("—" if showing["list_price"] is None
                 else f'{showing["list_price"]:.2f}')
    paid_cell = ("—" if showing["charged_price"] is None
                 else f'<strong>{showing["charged_price"]:.2f}</strong>')

    mode = "RESERVED" if showing["has_reserved_seating"] else "GA"
    flags = ""
    if showing["on_sale"] is False:
        flags = (f'<span class="rowflag">'
                 f'{esc(SALES_STATES.get(showing["sales_state"], "NOT ON SALE"))}</span>')

    return f"""
          <tr class="prow" data-venue="{esc(showing['venue'])}" data-mode="{mode}"
              data-starts="{esc(showing['starts_at'])}"
              data-filled="{pct_filled if pct_filled is not None else -1}"
              data-sold="{sold if sold is not None else -1}"
              data-left="{left if left is not None else -1}"
              data-price="{showing['charged_price'] if showing['charged_price'] is not None else -1}"
              data-velocity="{showing['sold_delta_24h'] if showing['sold_delta_24h'] is not None else -1}"
              data-level="{level}">
            <td class="c-when">{format_when(showing['starts_at'], compact=True)}</td>
            <td class="c-film">{title}{flags}</td>
            <td class="c-room" data-label="Room" data-venue="{esc(showing['venue'])}">{esc(showing['venue'])}<span class="mode mode-{mode.lower()}">{'RES' if mode == 'RESERVED' else 'GA'}</span></td>
            <td class="c-fill">{fill_cell}</td>
            <td class="c-seats" data-label="Sold">{seats}</td>
            <td class="c-left" data-label="Left">{left_cell}</td>
            <td class="c-list" data-label="Face value">{list_cell}</td>
            <td class="c-paid" data-label="At checkout">{paid_cell}</td>
            <td class="c-spark" data-label="Trend">{sparkline(showing['sold_history'])}</td>
            <td class="c-move" data-label="Sold in 6h">{signed(showing['sold_delta_6h'])}</td>
            <td class="c-move" data-label="Sold in 24h">{signed(showing['sold_delta_24h'])}</td>
          </tr>"""


def render_hud(summary):
    tiles = [
        ("SHOWINGS", summary["showings"]),
        ("SEATS SOLD", f"{summary['seats_sold']:,}"),
        ("SEATS LEFT", f"{summary['seats_left']:,}"),
        ("CAPACITY", f"{summary['capacity']:,}"),
    ]
    cells = "".join(f"""
          <div class="ptile">
            <span class="ptile-label">{label}</span>
            <span class="ptile-value">{value}</span>
          </div>""" for label, value in tiles)
    filled = (f"{summary['pct_filled']:.1f}% of capacity sold"
              if summary["pct_filled"] is not None else "no inventory data")
    return f"""
      <section class="hud">
        {cells}
      </section>
      <p class="hud-note">{filled} across {summary['with_inventory']} showings with data</p>
      """


def render_insights(showings):
    blocks = []
    for heading, rows, describe in insights(showings):
        if not rows:
            continue
        items = "".join(
            f"<li><span class=\"pinsight-what\">{esc(s['title'])}"
            f"<span class=\"pinsight-when\">{format_when(s['starts_at'])}"
            f" · {esc(s['venue'])}</span></span>"
            f"<span class=\"pinsight-value\">{describe(s)}</span></li>"
            for s in rows)
        blocks.append(f"""
        <div class="pinsight">
          <h3>{heading}</h3>
          <ul>{items}</ul>
        </div>""")
    if not blocks:
        return ""
    return f"""
      <section class="insights">
        {''.join(blocks)}
      </section>
      """


def render_html(showings, template_path, lookahead_days):
    with open(template_path, "r", encoding="utf-8") as handle:
        template = handle.read()

    summary = totals(showings)
    if showings:
        board = f"""
        <table class="board-table">
          <thead>
            <tr class="group-row">
              <th rowspan="2" class="c-when">Time</th>
              <th rowspan="2" class="c-film">Film</th>
              <th rowspan="2" class="c-room">Room</th>
              <th colspan="3" class="group">Seats</th>
              <th colspan="2" class="group">Price per ticket</th>
              <th colspan="3" class="group">Tickets sold</th>
            </tr>
            <tr>
              <th class="c-fill" title="Share of the room already sold">Full</th>
              <th class="c-seats" title="Tickets sold, out of the room's capacity">Sold</th>
              <th class="c-left" title="Tickets still for sale">Left</th>
              <th class="c-list" title="Face value of a standard adult ticket, before fees">Face</th>
              <th class="c-paid" title="What a buyer actually pays at checkout, fees included">Checkout</th>
              <th class="c-spark" title="Tickets sold over the last week of readings">Trend</th>
              <th class="c-move" title="Tickets sold in the last 6 hours">6h</th>
              <th class="c-move" title="Tickets sold in the last 24 hours">24h</th>
            </tr>
          </thead>
          <tbody id="boardRows">{''.join(render_row(s) for s in showings)}
          </tbody>
        </table>"""
    else:
        board = ('<div class="pempty">NO DATA · RUN PIPELINE</div>')

    venues = sorted({s["venue"] for s in showings if s["venue"]})
    venue_options = "".join(
        f'<option value="{esc(v)}">{esc(v)}</option>' for v in venues)

    generated = theatre_now().strftime("%a, %b %d %Y · %I:%M%p").replace(" 0", " ")

    return (template
            .replace("{{HUD}}", render_hud(summary))
            .replace("{{BOARD}}", board)
            .replace("{{INSIGHTS}}", render_insights(showings))
            .replace("{{VENUE_OPTIONS}}", venue_options)
            .replace("{{HOUSE_RULES}}", esc(house_rules(showings)))
            .replace("{{WINDOW_DAYS}}", str(lookahead_days))
            .replace("{{GENERATED_AT}}", esc(generated))
            .replace("{{SHOWING_COUNT}}", str(len(showings))))


def generate(db_name="movie_showtimes.db", output_dir=".",
             template_path=None, lookahead_days=LOOKAHEAD_DAYS):
    """Write power.html and power.json into output_dir."""
    here = os.path.dirname(os.path.abspath(__file__))
    template_path = template_path or os.path.join(here, "power_template.html")

    showings = load_showings(db_name, lookahead_days)
    print(f"Power dashboard: {len(showings)} showings in the next "
          f"{lookahead_days} days")

    os.makedirs(output_dir, exist_ok=True)

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
