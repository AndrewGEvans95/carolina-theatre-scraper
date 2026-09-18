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
# Sales states from the ticketing API; 2 is on sale now
SALES_STATES = {
    1: "BEFORE SALES",
    2: "ON SALE",
    3: "SALES CLOSED",
    4: "AFTER EVENT",
    5: "CUSTOM MESSAGE",
}
INSIGHT_LIMIT = 5


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


def format_when(starts_at):
    """"Fri, Sep 19 · 7:00pm" from a stored timestamp."""
    try:
        when = datetime.strptime(starts_at, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return esc(starts_at)
    day = when.strftime("%a, %b %d").replace(" 0", " ")
    clock = when.strftime("%I:%M%p").lower().lstrip("0")
    return f"{day} · {clock}"


def stat(label, value, extra=""):
    classes = f"pstat {extra}".strip()
    return (f"<div class=\"{classes}\"><dt>{label}</dt>"
            f"<dd>{value}</dd></div>")


def render_show(showing):
    """One board entry: everything about a showing, no drill-down needed."""
    pct_filled = showing["pct_filled"]
    # Band from the same rounded figure the label shows, so a bar reading
    # "70% FULL" isn't coloured as if it were 69%
    shown_pct = round(pct_filled) if pct_filled is not None else None
    level = fill_level(shown_pct)
    bar_width = pct_filled if pct_filled is not None else 0
    bar_label = (f"{shown_pct}% FULL" if shown_pct is not None
                 else "NO INVENTORY DATA")

    title = esc(showing["title"])
    if showing["ticket_url"]:
        title = (f"<a href=\"{esc(showing['ticket_url'])}\" target=\"_blank\" "
                 f"rel=\"noopener\">{title}</a>")

    flags = []
    if showing["max_per_order"]:
        flags.append(f"MAX {showing['max_per_order']}/ORDER")
    if showing["show_available_qty_on_web"] is False:
        flags.append("QTY HIDDEN ON WEB")
    if showing["on_sale"] is False:
        flags.append(esc(SALES_STATES.get(showing["sales_state"], "NOT ON SALE")))
    if showing["checked_at"]:
        flags.append(f"CHECKED {esc(showing['checked_at'][11:16])}")

    stats = "".join([
        stat("SOLD", showing["seats_sold"] if showing["seats_sold"] is not None else "—"),
        stat("LEFT", showing["seats_available"] if showing["seats_available"] is not None else "—"),
        stat("HELD", showing["seats_hold"] if showing["seats_hold"] is not None else "—"),
        stat("TOTAL", showing["seats_total"] if showing["seats_total"] is not None else "—"),
        stat("LIST", money(showing["list_price"]), "pstat-quiet"),
        stat("CHARGED", money(showing["charged_price"]), "pstat-strong"),
        stat("FEE", f"+{money(showing['fee'])[1:]}" if showing["fee"] is not None else "—"),
        stat("+6H", signed(showing["sold_delta_6h"])),
        stat("+24H", signed(showing["sold_delta_24h"])),
    ])

    mode = "RESERVED" if showing["has_reserved_seating"] else "GA"

    return f"""
        <article class="pshow" data-venue="{esc(showing['venue'])}" data-mode="{mode}"
                 data-starts="{esc(showing['starts_at'])}"
                 data-filled="{pct_filled if pct_filled is not None else -1}"
                 data-sold="{showing['seats_sold'] if showing['seats_sold'] is not None else -1}"
                 data-left="{showing['seats_available'] if showing['seats_available'] is not None else -1}"
                 data-price="{showing['charged_price'] if showing['charged_price'] is not None else -1}"
                 data-velocity="{showing['sold_delta_24h'] if showing['sold_delta_24h'] is not None else -1}"
                 data-onsale="{'1' if showing['on_sale'] is not False else '0'}">
          <div class="pshow-head">
            <span class="pshow-when">{format_when(showing['starts_at'])}</span>
            <h3 class="pshow-title">{title}</h3>
            <span class="pshow-venue" data-venue="{esc(showing['venue'])}">{esc(showing['venue'])}</span>
            <span class="pshow-mode pshow-mode-{mode.lower()}">{mode}</span>
          </div>
          <div class="pshow-bar" data-level="{level}" title="{bar_label}">
            <div class="pshow-bar-fill" style="width:{bar_width}%"></div>
            <span class="pshow-bar-label">{bar_label}</span>
          </div>
          <dl class="pshow-stats">{stats}</dl>
          <div class="pshow-flags">{' · '.join(flags)}</div>
        </article>
        """


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
        board = "".join(render_show(s) for s in showings)
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
