"""Conceptual structural grid and preliminary member-sizing engine.

The calculations are early-stage planning proxies only. They do not replace
structural analysis, geotechnical information, wind/seismic design, fire
engineering, material standards, or project-specific code checks.
"""
from __future__ import annotations

from math import ceil, isfinite
from typing import Any


def _bounded(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not isfinite(number):
        return default
    return max(low, min(high, number))


def generate_grid(
    width_m: float,
    depth_m: float,
    target_span_m: float = 7.5,
    orientation_deg: float = 0.0,
) -> dict[str, Any]:
    """Generate a regular rectangular conceptual column grid."""
    width = _bounded(width_m, 3.0, 300.0, 30.0)
    depth = _bounded(depth_m, 3.0, 300.0, 20.0)
    span = _bounded(target_span_m, 3.0, 15.0, 7.5)
    nx = max(1, int(ceil(width / span)))
    ny = max(1, int(ceil(depth / span)))
    x_spacing = width / nx
    y_spacing = depth / ny
    x = [round(i * x_spacing, 3) for i in range(nx + 1)]
    y = [round(i * y_spacing, 3) for i in range(ny + 1)]
    columns = [(round(xv, 3), round(yv, 3)) for xv in x for yv in y]
    return {
        "width_m": width,
        "depth_m": depth,
        "target_span_m": span,
        "orientation_deg": float(orientation_deg) % 360.0,
        "bays_x": nx,
        "bays_y": ny,
        "grid_lines_x": x,
        "grid_lines_y": y,
        "x_spacing_m": x_spacing,
        "y_spacing_m": y_spacing,
        "column_count": len(columns),
        "columns": columns,
        "tributary_area_m2": x_spacing * y_spacing,
    }


def preliminary_member_sizes(
    span_m: float,
    floor_load_kpa: float = 5.0,
    structural_system: str = "Reinforced concrete frame",
) -> dict[str, Any]:
    """Return conservative-looking conceptual starting sizes, not design sizes."""
    span = _bounded(span_m, 3.0, 15.0, 7.5)
    load = _bounded(floor_load_kpa, 1.0, 20.0, 5.0)
    system = str(structural_system or "Reinforced concrete frame").strip()
    if system == "Steel frame":
        beam_depth = max(250.0, span * 1000.0 / 20.0)
        column_width = max(250.0, (load * span * span) ** 0.5 * 35.0)
        slab = 130.0
    elif system == "Mass timber frame":
        beam_depth = max(300.0, span * 1000.0 / 18.0)
        column_width = max(250.0, (load * span * span) ** 0.5 * 30.0)
        slab = 180.0
    elif system == "Hybrid frame":
        beam_depth = max(300.0, span * 1000.0 / 18.0)
        column_width = max(300.0, (load * span * span) ** 0.5 * 32.0)
        slab = 160.0
    else:
        beam_depth = max(300.0, span * 1000.0 / 16.0)
        column_width = max(300.0, (load * span * span) ** 0.5 * 40.0)
        slab = max(150.0, span * 1000.0 / 30.0)
    beam_width = max(250.0, beam_depth * 0.5)
    return {
        "system": system,
        "governing_span_m": span,
        "floor_load_kpa": load,
        "conceptual_beam_width_mm": round(beam_width),
        "conceptual_beam_depth_mm": round(beam_depth),
        "conceptual_column_width_mm": round(column_width),
        "conceptual_slab_thickness_mm": round(slab),
        "warning": "Starting-point dimensions only. Do not use for construction or permit drawings without full structural analysis and code verification.",
    }


def structural_scheme_options(width_m: float, depth_m: float) -> list[dict[str, Any]]:
    """Compare common conceptual framing systems for the same floor plate."""
    systems = [
        ("Reinforced concrete frame", 7.5, "Robust general-purpose frame with familiar floor construction"),
        ("Steel frame", 9.0, "Longer-span option with lighter framing and rapid erection potential"),
        ("Mass timber frame", 7.0, "Lower-carbon structural concept with depth and fire strategy implications"),
        ("Hybrid frame", 8.5, "Mixed material strategy balancing span, mass and embodied-carbon goals"),
    ]
    results = []
    for name, target, strategy in systems:
        grid = generate_grid(width_m, depth_m, target)
        sizes = preliminary_member_sizes(max(grid["x_spacing_m"], grid["y_spacing_m"]), structural_system=name)
        spacing_variation = abs(grid["x_spacing_m"] - grid["y_spacing_m"]) / max(grid["x_spacing_m"], grid["y_spacing_m"], 1.0)
        efficiency = max(0.0, min(100.0, 100.0 - spacing_variation * 60.0 - grid["column_count"] * 0.5))
        results.append({
            "system": name,
            "strategy": strategy,
            "governing_span_m": max(grid["x_spacing_m"], grid["y_spacing_m"]),
            "bays_x": grid["bays_x"],
            "bays_y": grid["bays_y"],
            "column_count": grid["column_count"],
            "grid_efficiency_score": efficiency,
            **{k: v for k, v in sizes.items() if k.startswith("conceptual_")},
        })
    return results


def structural_summary(width_m: float, depth_m: float, target_span_m: float = 7.5, floor_load_kpa: float = 5.0, structural_system: str = "Reinforced concrete frame") -> dict[str, Any]:
    grid = generate_grid(width_m, depth_m, target_span_m)
    members = preliminary_member_sizes(max(grid["x_spacing_m"], grid["y_spacing_m"]), floor_load_kpa, structural_system)
    schemes = structural_scheme_options(width_m, depth_m)
    return {"grid": grid, "members": members, "schemes": schemes}
