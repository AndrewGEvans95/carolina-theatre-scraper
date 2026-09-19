"""Server-rendered dashboard. All inventory remains usable without JavaScript."""

import html
from collections import defaultdict
from datetime import datetime

from ui_components import asset_url, occupancy_meter


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def money(value):
    return f"${value:,.2f}" if value is not None else "—"


def number(value):
    return f"{value:,}" if value is not None else "—"


def delta(value):
    return f"+{value}" if value is not None and value > 0 else str(value) if value is not None else "—"


def render_showing(s):
    sid = esc(s["showing_id"])
    start = datetime.strptime(s["starts_at"], "%Y-%m-%d %H:%M")
    day = start.strftime("%a, %b %d").replace(" 0", " ")
    time = start.strftime("%I:%M%p").lower().lstrip("0")
    sold, total, left = s["seats_sold"], s["seats_total"], s["seats_available"]
    percent = s["pct_filled"]
    pct_label = f"{percent:g}%" if percent is not None else None
    description = f"{number(sold)} of {number(total)} seats sold; {number(left)} available"
    meter = occupancy_meter(percent, description, pct_label)
    mode = "Reserved" if s["has_reserved_seating"] else "General admission"
    state = {1: "Not yet on sale", 2: "On sale", 3: "Sales closed", 4: "Event ended", 5: "See box office"}.get(s["sales_state"], "Sale status unknown")
    flag = f'<span class="sale-flag">{esc(state)}</span>' if s["on_sale"] is not True else ""
    attributes = {
        "id": s["showing_id"], "title": s["title"], "venue": s["venue"],
        "mode": "reserved" if s["has_reserved_seating"] else "ga",
        "starts": s["starts_at"], "filled": percent, "sold": sold,
        "left": left, "total": total, "price": s["charged_price"],
        "velocity": s["sold_delta_24h"], "on-sale": str(s["on_sale"] is True).lower(),
    }
    attrs = " ".join(f'data-{key}="{esc(value)}"' for key, value in attributes.items())
    tiers = "".join(f'<tr><td>{esc(p.get("name"))}</td><td>{money(p.get("list"))}</td>'
                    f'<td>{money(p.get("charged"))}</td></tr>' for p in s["prices"])
    pricing = (f'<table class="price-tiers"><caption>Ticket prices</caption><thead><tr>'
               f'<th scope="col">Ticket</th><th scope="col">Base</th><th scope="col">With fees</th>'
               f'</tr></thead><tbody>{tiers}</tbody></table>' if tiers else '<p>Prices not reported for this showing.</p>')
    ticket = (f'<a class="primary-button" href="{esc(s["ticket_url"])}" target="_blank" rel="noopener">'
              f'Tickets <span aria-hidden="true">↗</span></a>' if s["ticket_url"] else "")
    checked = f'{esc(s["checked_at"])} UTC' if s["checked_at"] else "Not yet checked"
    return f'''
    <details class="showing" id="showing-{sid}" {attrs}>
      <summary aria-label="Details for {esc(s['title'])}, {day} at {time}">
        <span class="showing-film"><strong>{esc(s['title'])}</strong>
          <span class="showing-meta"><span class="venue-dot" aria-hidden="true"></span>{esc(s['venue'])}<span class="seat-mode">{mode}</span></span>{flag}</span>
        <span class="showing-when"><strong>{time}</strong><span>{day}</span></span>
        <span class="showing-occupancy" data-label="Seats sold">{meter}<span class="cell-note">{number(sold)} / {number(total)} sold</span></span>
        <span class="showing-left" data-label="Available"><strong>{number(left)}</strong><span class="cell-note">seats left</span></span>
        <span class="showing-price" data-label="Ticket"><strong>{money(s['charged_price'])}</strong><span class="cell-note">{money(s['fee'])} in fees</span></span>
        <span class="showing-activity" data-label="Sales / 24h"><strong>{delta(s['sold_delta_24h'])}</strong><span class="cell-note">{delta(s['sold_delta_6h'])} / 6h</span></span>
        <span class="expand-mark" aria-hidden="true">+</span>
      </summary>
      <div class="showing-details">
        <div>{pricing}<p class="detail-note">Prices in USD. The charged price includes fees.</p></div>
        <dl class="detail-facts"><div><dt>Held by theatre</dt><dd>{number(s['seats_hold'])} seats</dd></div>
          <div><dt>Order limit</dt><dd>{number(s['max_per_order'])} tickets</dd></div>
          <div><dt>Sale status</dt><dd>{esc(state)}</dd></div>
          <div><dt>Inventory checked</dt><dd>{checked}</dd></div></dl>
        <div class="detail-action">{ticket}<span>Showing #{sid}</span></div>
      </div>
    </details>'''


def render_dashboard(showings, template_path, lookahead_days, generated):
    from pathlib import Path
    template = Path(template_path).read_text(encoding="utf-8")
    days = defaultdict(list)
    for s in showings:
        days[s["starts_at"][:10]].append(s)
    max_count = max((len(rows) for rows in days.values()), default=1)
    day_buttons, day_options = [], []
    for date, rows in sorted(days.items()):
        day = datetime.strptime(date, "%Y-%m-%d")
        label = day.strftime("%a, %b %d").replace(" 0", " ")
        day_options.append(f'<option value="{date}">{label}</option>')
        day_buttons.append(f'<button class="day-signal" type="button" data-date="{date}" aria-pressed="false" '
                           f'aria-label="{label}, {len(rows)} showings"><span class="signal-count">{len(rows)}</span>'
                           f'<span class="signal-track"><span style="height:{len(rows)/max_count*100:.1f}%"></span></span>'
                           f'<span>{day.strftime("%a")}<b>{day.day:02d}</b></span></button>')
    known = [s for s in showings if s["seats_total"] and s["seats_sold"] is not None]
    capacity = sum(s["seats_total"] for s in known)
    sold = sum(s["seats_sold"] for s in known)
    left_rows = [s for s in showings if s["seats_available"] is not None]
    left = sum(s["seats_available"] for s in left_rows)
    pct = round(sold / capacity * 100, 1) if capacity else None
    values = {
        "STYLESHEET": asset_url("interface.css"), "SCRIPT": asset_url("power.js"),
        "BOARD": "".join(render_showing(s) for s in showings),
        "VENUE_OPTIONS": "".join(f'<option>{esc(v)}</option>' for v in sorted({s["venue"] for s in showings})),
        "DAY_OPTIONS": "".join(day_options), "DAY_SIGNALS": "".join(day_buttons),
        "WINDOW_DAYS": str(lookahead_days), "GENERATED_AT": esc(generated),
        "SHOWING_COUNT": str(len(showings)), "SOLD": number(sold) if known else "—",
        "LEFT": number(left) if left_rows else "—", "PERCENT": f"{pct:g}%" if pct is not None else "—",
        "COVERAGE": f"{len(known)} of {len(showings)} showings have sales data",
        "SUMMARY_METER": occupancy_meter(pct, "Percentage of known capacity sold"),
        "EMPTY_HIDDEN": "hidden" if showings else "",
    }
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template
