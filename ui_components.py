"""Shared, dependency-free presentation helpers for the static pages."""

import hashlib
import html
from pathlib import Path


def asset_url(name):
    """A changed asset gets a new URL even in a browser with cached CSS."""
    digest = hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()[:12]
    return f"{name}?v={digest}"


def occupancy_meter(percent, description="", label=None):
    """Keep the track visible at zero, and unknown inventory distinct from zero."""
    if percent is None:
        return ('<span class="occupancy is-unknown" title="Availability not reported">'
                '<span class="meter-track"></span>'
                '<span class="meter-label">No inventory</span></span>')
    percent = max(0, min(100, percent))
    level = "full" if percent >= 90 else "high" if percent >= 70 else "mid" if percent >= 40 else "low"
    label = label or f"{percent:g}% full"
    description = html.escape(description or label, quote=True)
    return (f'<span class="occupancy" data-level="{level}" title="{description}">'
            f'<span class="meter-track" role="meter" aria-label="Seats sold" '
            f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{percent:g}" '
            f'aria-valuetext="{description}">'
            f'<span class="meter-fill" style="width:{percent:g}%" '
            f'data-positive="{str(percent > 0).lower()}"></span></span>'
            f'<span class="meter-label">{html.escape(label)}</span></span>')
