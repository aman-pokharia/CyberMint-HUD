from __future__ import annotations

import math
from typing import Any


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """Convert a #RRGGBB string to a tuple of (r, g, b, a) floats in range [0.0, 1.0]."""
    cleaned = hex_color.strip().lstrip("#")
    if len(cleaned) != 6:
        return (0.0, 0.0, 0.0, alpha)
    try:
        r = int(cleaned[0:2], 16) / 255.0
        g = int(cleaned[2:4], 16) / 255.0
        b = int(cleaned[4:6], 16) / 255.0
        return (r, g, b, max(0.0, min(1.0, float(alpha))))
    except ValueError:
        return (0.0, 0.0, 0.0, alpha)


def chamfer_card_polygon(
    width: float,
    height: float,
    cut_top_right: float = 14.0,
    cut_bottom_left: float = 8.0,
) -> list[tuple[float, float]]:
    """
    Returns ordered polygon vertices for an authentic cyberpunk chamfered panel.
    - Top-left: standard corner (0, 0)
    - Top-right: 45-degree chamfer cut (width - cut_tr, 0) -> (width, cut_tr)
    - Bottom-right: standard corner (width, height)
    - Bottom-left: subtle 45-degree chamfer cut (cut_bl, height) -> (0, height - cut_bl)
    """
    w = max(width, 20.0)
    h = max(height, 20.0)
    ctr = min(cut_top_right, w * 0.3, h * 0.3)
    cbl = min(cut_bottom_left, w * 0.2, h * 0.2)

    return [
        (0.0, 0.0),
        (w - ctr, 0.0),
        (w, ctr),
        (w, h),
        (cbl, h),
        (0.0, h - cbl),
    ]


def compute_meter_segments(
    width: float,
    height: float,
    fraction: float,
    segment_width: float = 6.0,
    segment_gap: float = 2.0,
) -> list[dict[str, Any]]:
    """
    Calculates coordinates and state for a cyberpunk segmented HUD meter bar.
    Fraction is clamped between 0.0 and 1.0.
    """
    w = max(width, 10.0)
    h = max(height, 4.0)
    clamped_fraction = max(0.0, min(1.0, float(fraction)))

    step = segment_width + segment_gap
    num_segments = max(1, int((w - segment_gap) / step))
    filled_count = int(math.ceil(num_segments * clamped_fraction))

    segments = []
    for i in range(num_segments):
        x = segment_gap + i * step
        is_filled = i < filled_count
        # Cyberpunk warning threshold: top 25% of bar signals warning
        is_warning = is_filled and (i >= int(num_segments * 0.75))
        segments.append({
            "x": x,
            "y": 1.0,
            "width": segment_width,
            "height": max(2.0, h - 2.0),
            "filled": is_filled,
            "warning": is_warning,
        })
    return segments


def render_cyber_card(
    cr: Any,
    width: float,
    height: float,
    surface_rgba: tuple[float, float, float, float],
    primary_rgba: tuple[float, float, float, float],
    secondary_rgba: tuple[float, float, float, float],
    scale: float = 1.0,
) -> None:
    """
    Renders a cyberpunk card background with Cairo:
    - Translucent obsidian body
    - Chamfered top-right and bottom-left edges
    - Neon primary hairline outline
    - Neon secondary (cyan) tech bracket accents
    """
    if cr is None:
        return

    cut_tr = 14.0 * scale
    cut_bl = 8.0 * scale
    pts = chamfer_card_polygon(width, height, cut_tr, cut_bl)

    # 1. Fill card interior with dark surface
    cr.new_path()
    cr.move_to(pts[0][0], pts[0][1])
    for pt in pts[1:]:
        cr.line_to(pt[0], pt[1])
    cr.close_path()
    cr.set_source_rgba(*surface_rgba)
    cr.fill_preserve()

    # 2. Stroke perimeter with subtle primary accent (neon red hairline)
    cr.set_source_rgba(primary_rgba[0], primary_rgba[1], primary_rgba[2], 0.65)
    cr.set_line_width(1.0 * scale)
    cr.stroke()

    # 3. Draw cyan tech accent brackets at the top-left and chamfer corner
    cr.set_source_rgba(secondary_rgba[0], secondary_rgba[1], secondary_rgba[2], 0.95)
    cr.set_line_width(2.0 * scale)

    # Top-left cyber bracket
    bracket_len = 16.0 * scale
    cr.move_to(0.0, bracket_len)
    cr.line_to(0.0, 0.0)
    cr.line_to(bracket_len, 0.0)
    cr.stroke()

    # Chamfer tech cut highlight
    cr.move_to(width - cut_tr - 8.0 * scale, 0.0)
    cr.line_to(width - cut_tr, 0.0)
    cr.line_to(width, cut_tr)
    cr.line_to(width, cut_tr + 8.0 * scale)
    cr.stroke()

    # Bottom tech bracket notch
    notch_len = 10.0 * scale
    cr.move_to(cut_bl + notch_len, height)
    cr.line_to(cut_bl, height)
    cr.line_to(0.0, height - cut_bl)
    cr.stroke()


def render_cyber_meter(
    cr: Any,
    width: float,
    height: float,
    fraction: float | None,
    primary_rgba: tuple[float, float, float, float],
    secondary_rgba: tuple[float, float, float, float],
    scale: float = 1.0,
    is_active: bool = True,
) -> None:
    """
    Renders a cyberpunk segmented telemetry bar with Cairo:
    - Dark trough track
    - Glowing cyan segments for normal range
    - Neon red segments for critical / high load (> 75%)
    - Empty dimmed track when inactive or metric is unavailable
    """
    if cr is None:
        return

    # Draw trough background
    cr.set_source_rgba(0.08, 0.09, 0.13, 0.8)
    cr.rectangle(0, 0, width, height)
    cr.fill()

    # Trough thin frame
    cr.set_source_rgba(secondary_rgba[0], secondary_rgba[1], secondary_rgba[2], 0.25)
    cr.set_line_width(1.0)
    cr.rectangle(0.5, 0.5, max(1.0, width - 1.0), max(1.0, height - 1.0))
    cr.stroke()

    if not is_active or fraction is None:
        # Metric unavailable: draw a faint diagonal warning hash pattern
        cr.set_source_rgba(primary_rgba[0], primary_rgba[1], primary_rgba[2], 0.2)
        cr.set_line_width(1.0)
        step = 10.0 * scale
        x = 0.0
        while x < width:
            cr.move_to(x, height)
            cr.line_to(x + 6.0 * scale, 0.0)
            x += step
        cr.stroke()
        return

    seg_w = max(3.0, 6.0 * scale)
    seg_gap = max(1.5, 2.0 * scale)
    segments = compute_meter_segments(width, height, fraction, seg_w, seg_gap)

    for seg in segments:
        if seg["filled"]:
            if seg["warning"]:
                # High load warning: Neon red fill with bright highlight
                cr.set_source_rgba(primary_rgba[0], primary_rgba[1], primary_rgba[2], 0.95)
            else:
                # Normal operational load: Neon cyan
                cr.set_source_rgba(secondary_rgba[0], secondary_rgba[1], secondary_rgba[2], 0.90)
            cr.rectangle(seg["x"], seg["y"], seg["width"], seg["height"])
            cr.fill()
        else:
            # Unfilled track segment
            cr.set_source_rgba(0.15, 0.18, 0.24, 0.45)
            cr.rectangle(seg["x"], seg["y"], seg["width"], seg["height"])
            cr.fill()
